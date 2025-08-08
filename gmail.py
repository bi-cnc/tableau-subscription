import os
import json
import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from googleapiclient.discovery import build
from google.oauth2 import service_account as SACredentials

from configuration import Configuration


class Gmail:
    def __init__(self, root_directory="/data", code_directory="/code"):
        # základní logging, pokud ještě není nastaven
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

        self.cfg = Configuration(root_directory, code_directory)
        self.creds = None
        self.service = None

    # ---------- interní utility ----------

    @staticmethod
    def _clean_sa_keys(d: dict) -> dict:
        """Odstraní '#' z názvů klíčů (např. '#private_key' -> 'private_key')."""
        return {k.lstrip("#"): v for k, v in d.items()}

    @staticmethod
    def _safe_preview(d: dict) -> dict:
        """
        Bezpečný náhled hodnot pro log:
        - private_key a refresh token úplně skryjeme
        - ostatní dlouhé stringy zkrátíme
        """
        def mask(k, v):
            if not isinstance(v, str):
                return v
            kl = k.lower()
            if "private_key" in kl or "refresh_token" in kl:
                return "<hidden>"
            if v.startswith("-----BEGIN PRIVATE KEY-----"):
                return "<hidden-pem>"
            return v[:20] + "..." if len(v) > 20 else v

        return {k: mask(k, v) for k, v in d.items()}

    @staticmethod
    def _mime_to_raw(message_obj: MIMEMultipart) -> dict:
        """Převede MIME zprávu na raw base64 (formát pro Gmail API)."""
        raw = base64.urlsafe_b64encode(message_obj.as_bytes()).decode("utf-8")
        return {"raw": raw}

    # ---------- veřejné metody ----------

    def gmail_login(self):
        """
        Přihlášení k Gmail API:
        - vezmeme service_account_post z image_parameters (Keboola je do configu merguje ze Stack/Image params)
        - odstraníme '#' z klíčů
        - vytvoříme Credentials a službu Gmail API
        - impersonujeme self.cfg.gmail_address
        """
        service_account_info = self.cfg.service_account_post
        if not service_account_info:
            raise Exception("Missing 'service_account_post' in merged image_parameters!")

        # DEBUG náhled – bezpečný
        logging.debug("==== DEBUG: service_account_post (safe) ====")
        logging.debug(json.dumps(self._safe_preview(service_account_info), indent=2))
        logging.debug("============================================")

        # Odstraníme '#' z názvů klíčů (Keboola je takhle vrací, když jsou šifrované)
        clean_info = self._clean_sa_keys(service_account_info)

        # Zalogujeme jen názvy klíčů po očištění (pro jistotu)
        logging.debug("==== DEBUG: service_account_post (cleaned keys) ====")
        logging.debug(json.dumps(list(clean_info.keys()), indent=2))
        logging.debug("====================================================")

        # Kontrola povinných polí pro service account
        required_keys = ["type", "client_email", "private_key"]
        missing = [k for k in required_keys if k not in clean_info or not clean_info[k]]
        if missing:
            raise Exception(f"Service account info missing required keys: {missing}")

        # Scopes pro posílání emailů
        SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

        # Impersonace – posílat jménem této adresy
        user_to_impersonate = self.cfg.gmail_address
        if not user_to_impersonate:
            raise Exception("Missing 'gmail_address' in parameters!")

        # Credentials + Gmail service
        self.creds = SACredentials.Credentials.from_service_account_info(clean_info, scopes=SCOPES).with_subject(user_to_impersonate)
        self.service = build("gmail", "v1", credentials=self.creds)

        logging.info("Gmail service initialized and impersonation set.")

    def construct_message(self, subject: str, to: str, text: str) -> MIMEMultipart:
        """Sestaví jednoduchou textovou zprávu (MIME)."""
        if not subject or not to or not text:
            raise ValueError("Missing required email fields: 'subject', 'to', or 'text'")

        msg = MIMEMultipart()
        msg.attach(MIMEText(text, "plain"))
        msg["Subject"] = subject
        msg["To"] = to
        msg["From"] = self.cfg.gmail_address
        return msg

    def attach_to_message(self, message: MIMEMultipart, attachment_bytes: bytes, attachment_name: str, file_type: str) -> MIMEMultipart:
        """
        Přidá přílohu do zprávy.
        file_type může být např. 'crosstab/excel' (xls), jinak použijeme octet-stream.
        """
        if file_type == "crosstab/excel":
            mime_main = "application"
            mime_sub = "vnd.ms-excel"
        else:
            mime_main = "application"
            mime_sub = "octet-stream"

        mime_base = MIMEBase(mime_main, mime_sub)
        mime_base.set_payload(attachment_bytes)
        encoders.encode_base64(mime_base)
        mime_base.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
        message.attach(mime_base)
        return message

    def send_email(self, to: str, raw_message_string: str = None, message_obj: MIMEMultipart = None):
        """
        Odeslání emailu.
        - Buď předáš už hotový raw string (base64 MIME) v `raw_message_string`
        - Nebo předáš `message_obj` typu MIMEMultipart a my ho převedeme na raw
        """
        if not self.service:
            raise RuntimeError("Gmail service not initialized. Call gmail_login() first.")

        if raw_message_string is None and message_obj is None:
            raise ValueError("Provide either 'raw_message_string' or 'message_obj'.")

        if message_obj is not None:
            body = self._mime_to_raw(message_obj)
        else:
            body = {"raw": base64.urlsafe_b64encode(raw_message_string.encode("utf-8")).decode("utf-8")}

        try:
            resp = self.service.users().messages().send(userId="me", body=body).execute()
            logging.info(f"Message sent successfully: {resp.get('id')}")
            return resp
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            raise
