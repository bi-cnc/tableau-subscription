import json
import mimetypes
import googleapiclient
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build
from configuration import Configuration


def o_print(message, opt=True):
    if opt:
        print(message)


class Chat:

    def __init__(self, root_directory, code_directory):
        self.cfg = Configuration(root_directory, code_directory)
        self.g_chat_s = self.authenticate_google_chat()
        self.g_drive_s = self.authenticate_google_drive()
        self.share_url = None

    def authenticate_google_drive(self, p=False):
        try:
            o_print("Using token authorization", opt=p)
            creds = Credentials.from_authorized_user_info(info=self.cfg.user_token)
        except:
            o_print("Token authorization failed", opt=p)
        else:
            o_print("Token authorization successful", opt=p)
            self.g_drive_s = build('drive', 'v3', credentials=creds)
        return self.g_drive_s

    def upload(self, file_name, file_path, mime_type=None, p=False):
        if self.g_drive_s is None:
            self.authenticate_google_drive()
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(file_path)

        o_print(f'Mime_type: {mime_type}', opt=p)
        folder_id = self.cfg.folder_id
        if folder_id == '':
            file_metadata = {'name': file_name}
            o_print("Uploading outside folder", opt=p)
        else:
            file_metadata = {'name': file_name, 'parents': [folder_id]}
            o_print("Uploading inside folder", opt=p)

        media = googleapiclient.http.MediaFileUpload(file_path, mimetype=mime_type)
        file = self.g_drive_s.files().create(body=file_metadata, media_body=media, fields='id').execute()
        o_print(f'File ID: {file.get("id")}', opt=p)

        file_id = file.get('id')
        permission = {'type': 'anyone', 'role': 'reader'}
        self.g_drive_s.permissions().create(fileId=file_id, body=permission).execute()

        file = self.g_drive_s.files().get(fileId=file_id, fields='webViewLink').execute()
        self.share_url = file.get('webViewLink')
        o_print(f'Share URL:{self.share_url}', opt=p)
        return self.share_url

    @staticmethod
    def _clean_sa_keys(d: dict) -> dict:
        return {k.lstrip("#"): v for k, v in d.items()}

    @staticmethod
    def _safe_preview(d: dict) -> dict:
        def mask(k, v):
            if not isinstance(v, str):
                return v
            lk = k.lower()
            if "private_key" in lk or "refresh_token" in lk:
                return "<hidden>"
            if v.startswith("-----BEGIN PRIVATE KEY-----"):
                return "<hidden-pem>"
            return v[:20] + "..." if len(v) > 20 else v
        return {k: mask(k, v) for k, v in d.items()}

    def authenticate_google_chat(self, p=False):
        try:
            sa_info = self.cfg.image_params["service_account_post"]

            # Debug log - safe
            print("==== DEBUG: service_account_post for Chat (safe) ====")
            print(json.dumps(self._safe_preview(sa_info), indent=2))
            print("====================================================")

            clean_info = self._clean_sa_keys(sa_info)

            # Kontrola povinných polí
            required = ["type", "client_email", "private_key"]
            missing = [k for k in required if not clean_info.get(k)]
            if missing:
                raise Exception(f"Google Chat SA missing required keys: {missing}")

            SCOPES = ["https://www.googleapis.com/auth/chat.bot"]
            credentials = SACredentials.from_service_account_info(clean_info, scopes=SCOPES)
            chat = build('chat', 'v1', credentials=credentials)

        except Exception as e:
            print("Google chat authentication failed. Check your service account credentials file")
            raise e
        else:
            o_print("Google chat authentication successful", opt=p)
            return chat

    def share_to_gchat(self, space_id, message_text=None, p=False):
        if self.g_chat_s is None:
            self.g_chat_s = self.authenticate_google_chat()
        if self.share_url is None:
            print("Google chat has no attachment, no message sent")
            return

        if message_text is None:
            text_1 = f'Odkaz na google drive\n{self.share_url}'
        else:
            text_1 = f'{message_text}\nOdkaz na google drive:\n{self.share_url}'

        message_simple = {'text': text_1}
        try:
            self.g_chat_s.spaces().messages().create(parent=f'spaces/{space_id}', body=message_simple).execute()
            o_print('File shared successfully.', p)
        except:
            print('An error occurred while sending message')
        else:
            o_print('Message sent.', p)
