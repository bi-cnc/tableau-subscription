import pandas as pd
import json
import re
import unidecode
import os
import glob
import time
import requests
from PyPDF2 import PdfMerger

from configuration import Configuration
from Tableau_driver import Tableau
from gmail import Gmail
from exceptions import UserException

# seconds to wait before each retry of a failed attachment download
RETRY_WAITS = [10, 30, 60]
# (connect, read) timeout of one attachment download in seconds
REQUEST_TIMEOUT = (10, 300)


class AttachmentError(Exception):
    pass


class Driver:

    def __init__(self, root_directory, code_directory):
        print(">>> DRIVER INIT STARTED")
        self.cfg = Configuration(root_directory, code_directory)
        print(">>> CONFIGURATION LOADED")

        self.cfg.get_input_data()
        print(">>> INPUT DATA LOADED")

        self.cfg.filter_emails()
        print(">>> EMAILS FILTERED")

        self.cfg.filter_subscribers()
        print(">>> SUBSCRIBERS FILTERED")

        self.tableau = Tableau(self.cfg)
        print(">>> TABLEAU OBJECT CREATED")

        self.cfg.identify_attachments(self.tableau)
        print(">>> ATTACHMENTS IDENTIFIED")

        self.s = self.tableau.login()
        print(">>> TABLEAU LOGIN SUCCESS")

        self.gmail = Gmail(root_directory, code_directory)
        self.gmail.gmail_login()
        print(">>> GMAIL LOGIN SUCCESS")
        print(">>> DRIVER INIT FINISHED")

    def run(self):
        skipped = []
        for email_index, email in self.cfg.email_queue.iterrows():
            print(f"Processing: {email.EMAIL_ID}.")
            temp_active_subscribers = self.cfg.active_subscribers.loc[
                self.cfg.active_subscribers.GROUP_ID == email.GROUP_ID
            ]
            temp_current_attachments = self.cfg.current_attachments.loc[
                self.cfg.current_attachments.EMAIL_ID == email.EMAIL_ID
            ]

            if temp_current_attachments.empty and not temp_active_subscribers.empty:
                print(f"""No attachment for email with EMAIL_ID: {email.EMAIL_ID}, please check input tables""")
                skipped.append((email.EMAIL_ID, "all subscribers", "no attachment in input tables"))
                continue

            for subsc_index, subsc in temp_active_subscribers.iterrows():
                to = self.set_recepients(email, subsc)
                try:
                    msg = self.build_message(email, subsc, to, temp_current_attachments)
                except AttachmentError as e:
                    print(f"Skipped email: {email.EMAIL_ID} on {to}. {e}")
                    skipped.append((email.EMAIL_ID, to, str(e)))
                    continue

                self.gmail.send_email(to, msg.as_string())
                print(f"Sent email: {email.EMAIL_ID} in {email.MODE} mode on {to}")

        if skipped:
            lines = [f"- {email_id} | {to} | {reason}" for email_id, to, reason in skipped]
            raise UserException(
                f"{len(skipped)} email(s) were not sent (EMAIL_ID | recipient | reason):\n" + "\n".join(lines)
            )
        return 0

    def build_message(self, email, subsc, to, attachments):
        txt = self.compile_msg(email.MESSAGE, subsc)
        subject = self.compile_msg(email.SUBJECT, subsc)
        msg = self.gmail.construct_message(
            to=to,
            subject=subject,
            text=txt,
        )

        pdf_merger = PdfMerger()
        try:
            for attach_index, attach in attachments.iterrows():
                url_params = self.compile_params(attach, subsc)
                url = self.construct_attachment_url(attach)
                attachment_name = self.attachment_name(attach, url_params)
                resp = self.download_attachment(url, url_params)

                if (email.MERGE_ATTACHMENTS == 'merge') and (attach.ATTACHMENT_TYPE == 'pdf'):
                    tmp_path = f'{self.cfg.root}/out/tmp_{attach_index}.pdf'
                    with open(tmp_path, 'wb') as f:
                        f.write(resp.content)
                    try:
                        pdf_merger.append(tmp_path)
                    except Exception as e:
                        raise AttachmentError(f"Error appending PDF {tmp_path} (url: {url}, url_params: {url_params}): {e}")
                else:
                    msg = self.gmail.attach_to_message(msg, resp.content, attachment_name, attach.ATTACHMENT_TYPE)

            if email.MERGE_ATTACHMENTS == 'merge':
                if os.path.exists(f'{self.cfg.root}/out/report.pdf'):
                    os.remove(f'{self.cfg.root}/out/report.pdf')
                with open(f'{self.cfg.root}/out/report.pdf', 'wb') as output_file:
                    pdf_merger.write(output_file)

                with open(f'{self.cfg.root}/out/report.pdf', 'rb') as f:
                    msg = self.gmail.attach_to_message(msg, f.read(), "report.pdf", "pdf")
        finally:
            pdf_merger.close()
            # cleanup temporary PDF parts
            for f in glob.glob(f"{self.cfg.root}/out/tmp_*.pdf"):
                os.remove(f)

        return msg

    def download_attachment(self, url, url_params):
        last_error = ""
        for wait in [0] + RETRY_WAITS:
            if wait:
                print(f"Retrying download in {wait} s. Last error: {last_error[:300]}")
                time.sleep(wait)
            try:
                resp = self.s.get(url, params=url_params, timeout=REQUEST_TIMEOUT)
            except requests.exceptions.RequestException as e:
                last_error = f"{type(e).__name__}: {e}"
                continue

            if resp.status_code == 200:
                print("Successfully called: " + resp.url)
                return resp

            last_error = f"HTTP {resp.status_code}: {resp.text}"
            if not self.is_transient(resp):
                break

        raise AttachmentError(
            f"Download of attachment fails. url: {url}, url_params: {url_params} with server response: {last_error}"
        )

    @staticmethod
    def is_transient(resp):
        # 5xx, rate limit and Tableau export error 400080 pass on a later attempt
        return resp.status_code >= 500 or resp.status_code == 429 or (
            resp.status_code == 400 and "400080" in resp.text
        )

    def compile_msg(self, text, subsc):
        tags_to_replace = re.findall("{[^\s]+}", text)
        tags_to_search = [re.search("[^{}]+", tag).group(0) for tag in tags_to_replace]

        output_msg = text
        message_loads = json.loads(subsc.MESSAGE_LOADS) if pd.notna(subsc.MESSAGE_LOADS) else {}
        filter_loads = json.loads(subsc.FILTER_PAYLOAD) if pd.notna(subsc.FILTER_PAYLOAD) else {}

        for tag in tags_to_search:
            if tag in message_loads:
                output_msg = output_msg.replace("{" + tag + "}", message_loads[tag])
            if tag in filter_loads:
                output_msg = output_msg.replace("{" + tag + "}", str(filter_loads[tag]))

        return output_msg

    def set_recepients(self, email, subsc):
        if email.MODE == "test":
            return email.OWNER
        elif email.MODE == "run":
            return subsc.EMAIL
        elif email.MODE == "send me a copy":
            return subsc.EMAIL + "," + email.OWNER
        else:
            raise Exception(
                f"Unexpected MODE in email ~{email.EMAIL_ID}~. Please configure mode to 'test', 'run' or 'send me a copy'. Or set mode to 'deprecated'."
            )

    def compile_params(self, attach, subsc):
        filter_loads = json.loads(subsc.FILTER_PAYLOAD) if pd.notna(subsc.FILTER_PAYLOAD) else {}
        filter_fields = json.loads(attach.FILTER_FIELDS) if pd.notna(attach.FILTER_FIELDS) else []

        output_params = {}
        for field in filter_fields:
            if isinstance(field, str) and field in filter_loads:
                output_params["vf_" + field] = filter_loads[field]
            elif isinstance(field, dict):
                output_params.update(field)

        return output_params

    def construct_attachment_url(self, attach):
        if attach.TABLEAU_OBJECT == "view":
            object_class = "views"
            if attach.ATTACHMENT_TYPE not in self.cfg.allowed_view_format:
                raise Exception(
                    f"Unexpected ATTACHMENT_TYPE in attachment ~{attach.LUID}~. Specify ATTACHMENT_TYPE from {self.cfg.allowed_view_format} for 'view'."
                )
        elif attach.TABLEAU_OBJECT == "workbook":
            object_class = "workbooks"
            if attach.ATTACHMENT_TYPE not in self.cfg.allowed_workbook_format:
                raise Exception(
                    f"Unexpected ATTACHMENT_TYPE in attachment ~{attach.LUID}~. Specify ATTACHMENT_TYPE from {self.cfg.allowed_workbook_format} for 'workbook'."
                )
        else:
            raise Exception(
                f"Unexpected TABLEAU_OBJECT in attachment ~{attach.LUID}~. Use 'view' or 'workbook'."
            )

        return f"{self.tableau.base_url}sites/{self.tableau.site_id}/{object_class}/{attach.LUID}/{attach.ATTACHMENT_TYPE}"

    def attachment_name(self, attach, url_params):
        ext_map = {
            "image": ".jpeg",
            "content": ".twbx",
            "data": ".csv",
            "pdf": ".pdf",
            "powerpoint": ".pptx",
            "crosstab/excel": ".xlsx"
        }
        self.ending = ext_map.get(attach.ATTACHMENT_TYPE, ".dat")
        joined_params = "_".join(url_params.values())
        name = f"{attach.WORKBOOK}_{attach.VIEW}_{joined_params}{self.ending}"
        return unidecode.unidecode(name)
