import pandas as pd
import json
import re
import unidecode
import mimetypes
import os
import glob
from PyPDF2 import PdfMerger

from configuration import Configuration
from Tableau_driver import Tableau
from gmail import Gmail
from chat import Chat


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

        self.chat = Chat(root_directory, code_directory)
        print(">>> CHAT OBJECT CREATED")
        print(">>> DRIVER INIT FINISHED")

    def run(self):
        for email_index, email in self.cfg.email_queue.iterrows():
            print(f"Processing: {email.EMAIL_ID}.")
            temp_active_subscribers = self.cfg.active_subscribers.loc[
                self.cfg.active_subscribers.GROUP_ID == email.GROUP_ID
            ]
            temp_current_attachments = self.cfg.current_attachments.loc[
                self.cfg.current_attachments.EMAIL_ID == email.EMAIL_ID
            ]

            for subsc_index, subsc in temp_active_subscribers.iterrows():
                txt = self.compile_msg(email.MESSAGE, subsc)
                subject = self.compile_msg(email.SUBJECT, subsc)
                to = self.set_recepients(email, subsc)
                msg = self.gmail.construct_message(
                    to=to,
                    subject=subject,
                    text=txt,
                )

                pdf_merger = PdfMerger()

                if temp_current_attachments.empty:
                    print(f"""No attachment for email with EMAIL_ID: {email.EMAIL_ID}, please check input tables""")
                    return

                for attach_index, attach in temp_current_attachments.iterrows():
                    url_params = self.compile_params(attach, subsc)
                    url = self.construct_attachment_url(attach)
                    attachment_name = self.attachment_name(attach, url_params)
                    resp = self.s.get(url, params=url_params)
                    if resp.status_code != 200:
                        raise Exception(
                            f"Download of attachment fails. url: {url}, url_params: {url_params} with server response: {resp.text}"
                        )
                    else:
                        print("Successfully called: " + resp.url)

                    if (email.MERGE_ATTACHMENTS == 'merge') and (attach.ATTACHMENT_TYPE == 'pdf'):
                        tmp_path = f'{self.cfg.root}/out/tmp_{attach_index}.pdf'
                        with open(tmp_path, 'wb') as f:
                            f.write(resp.content)
                        try:
                            pdf_merger.append(tmp_path)
                        except Exception as e:
                            print(f"\u274c Error appending PDF {tmp_path}: {e}")
                    else:
                        if "@" in to:
                            msg = self.gmail.attach_to_message(msg, resp.content, attachment_name, attach.ATTACHMENT_TYPE)
                        else:
                            temp_address = f'{self.cfg.root}/out/tmp{self.ending}'
                            if os.path.exists(temp_address):
                                os.remove(temp_address)
                            with open(f'{self.cfg.root}/out/tmp.pdf', 'wb') as f:
                                f.write(resp.content)
                            self.chat.upload(attachment_name, f'{self.cfg.root}/out/report.pdf')

                if email.MERGE_ATTACHMENTS == 'merge':
                    if os.path.exists(f'{self.cfg.root}/out/report.pdf'):
                        os.remove(f'{self.cfg.root}/out/report.pdf')
                    with open(f'{self.cfg.root}/out/report.pdf', 'wb') as output_file:
                        pdf_merger.write(output_file)
                    pdf_merger.close()

                    # cleanup temporary PDF parts
                    for f in glob.glob(f"{self.cfg.root}/out/tmp_*.pdf"):
                        os.remove(f)

                    if "@" in to:
                        with open(f'{self.cfg.root}/out/report.pdf', 'rb') as f:
                            msg = self.gmail.attach_to_message(msg, f.read(), "report.pdf", "pdf")
                    else:
                        self.chat.upload(attachment_name, f"./report.pdf")

                if "@" in to:
                    self.gmail.send_email(to, msg.as_string())
                    print(f"Sent email: {email.EMAIL_ID} in {email.MODE} mode on {to}")
                else:
                    self.chat.share_to_gchat(to, txt)
                    print(f"Sent chat: {email.EMAIL_ID} in {email.MODE} mode to space {to}")

        return 0

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
