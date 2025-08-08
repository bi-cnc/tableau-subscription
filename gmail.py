import os
import json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials as SACredentials

from configuration import Configuration


class Gmail:
    def __init__(self, root_directory="/data", code_directory="/code"):
        self.cfg = Configuration(root_directory, code_directory)
        self.creds = None

    def gmail_login(self):
        SCOPES = ['https://www.googleapis.com/auth/gmail.send']

        # Načtení service account dat
        service_account_info = self.cfg.image_params.get("service_account_post")
        if not service_account_info:
            raise Exception("Missing 'service_account_post' in image_parameters or stack parameters!")

        # --- DEBUG BEZPEČNÝ VÝPIS ---
        safe_dump = {
            k: (v[:20] + "...") if isinstance(v, str) and len(v) > 20 else v
            for k, v in service_account_info.items()
        }
        print("==== DEBUG: service_account_post (safe) ====")
        print(json.dumps(safe_dump, indent=2))
        print("============================================")

        user_to_impersonate = self.cfg.gmail_address
        if not user_to_impersonate:
            raise Exception("Missing 'gmail_address' in parameters!")

        # Přihlášení pomocí service account
        self.creds = SACredentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES
        ).with_subject(user_to_impersonate)

        service = build('gmail', 'v1', credentials=self.creds)
        return service

    def send_email(self, to, raw_message_string):
        try:
            raw_message = base64.urlsafe_b64encode(raw_message_string.encode('utf-8')).decode('utf-8')
            raw_message = {'raw': raw_message}

            service = build('gmail', 'v1', credentials=self.creds)
            message = service.users().messages().send(userId='me', body=raw_message).execute()
            print(f"Message sent successfully: {message['id']}")
        except Exception as error:
            print(f"Failed to send email: {error}")

    def construct_message(self, subject, to, text):
        if not subject or not to or not text:
            raise ValueError("Missing required email fields: 'subject', 'to', or 'text'")

        message = MIMEMultipart()
        message.attach(MIMEText(text, "plain"))
        message["Subject"] = subject
        message["To"] = to
        message["From"] = self.cfg.gmail_address
        return message

    def attach_to_message(self, message, attachment, attachment_name, file_type):
        if file_type == "crosstab/excel":
            mime_type = 'application/vnd.ms-excel'
        else:
            mime_type = 'application/octet-stream'

        mime_base = MIMEBase('application', mime_type)
        mime_base.set_payload(attachment)
        encoders.encode_base64(mime_base)
        mime_base.add_header('Content-Disposition', f'attachment; filename={attachment_name}')
        message.attach(mime_base)
        return message
