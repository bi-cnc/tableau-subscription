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
        SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

        # stack params primárně, fallback image_params (pokud Storage API mergne)
        sa_post = self.cfg.service_account_post or self.cfg.image_params.get("service_account_post", {})
        print("🔎 gmail_login: service_account_post keys:", list(sa_post.keys()) if isinstance(sa_post, dict) else type(sa_post))

        if not sa_post:
            raise Exception("Missing 'service_account_post' in stack/image parameters!")

        user_to_impersonate = self.cfg.gmail_address
        print("🔎 gmail_login: gmail_address present:", bool(user_to_impersonate))
        if not user_to_impersonate:
            raise Exception("Missing 'gmail_address' in parameters!")

        # sanity check
        for k in ("type", "client_email", "private_key"):
            if k not in sa_post or not sa_post[k]:
                raise Exception(f"Missing '{k}' in service_account_post!")

        self.creds = (
            SACredentials.from_service_account_info(sa_post, scopes=SCOPES)
            .with_subject(user_to_impersonate)
        )

        print("✅ gmail_login: service account credentials created.")
        return build("gmail", "v1", credentials=self.creds)

    def send_email(self, to, raw_message_string):
        try:
            raw_message = base64.urlsafe_b64encode(raw_message_string.encode('utf-8')).decode('utf-8')
            raw_message = {'raw': raw_message}

            service = build('gmail', 'v1', credentials=self.creds)
            message = service.users().messages().send(userId='me', body=raw_message).execute()
            print(f"✅ Message sent: {message.get('id')}")
        except Exception as error:
            print(f"❌ Failed to send email: {error}")

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
