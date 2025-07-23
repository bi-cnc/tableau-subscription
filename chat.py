

##### chat.py


import googleapiclient
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
import mimetypes
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
        # Getting authorization. If no token exist token must be generated done manually.
        # Returns authenticated service
        # Authenticating
        try:
            o_print("Using token authorization", opt=p)
            creds = Credentials.from_authorized_user_info(info=self.cfg.user_token)

        except:
            o_print("Token authorization failed", opt=p)

        else:
            o_print("Token authorization successful", opt=p)
            # Authenticate the API client
            self.g_drive_s = build('drive', 'v3', credentials=creds)
        return self.g_drive_s

    def upload(self, file_name, file_path, mime_type=None, p=False):
        # Uploads file to google drive.
        # service, built returned by authenticate_service function
        if self.g_drive_s is None:
            self.authenticate_google_drive()
        if mime_type is None:
                mime_type, _ = mimetypes.guess_type(file_path)

        # Set the MIME type of the file to upload
        #mime_type = 'image/png'

        o_print(f'Mime_type: {mime_type}',opt=p)
        # Create a new file metadata
        folder_id = self.cfg.folder_id
        if folder_id == '':
            file_metadata = {'name': file_name}
            o_print("Uploading outside folder", opt=p)
        else:
            file_metadata = {'name': file_name, 'parents': [folder_id]}
            o_print("Uploading inside folder", opt=p)
        # Create a media upload object for the file
        media = googleapiclient.http.MediaFileUpload(file_path, mimetype=mime_type)

        # Upload the file to Google Drive
        file = self.g_drive_s.files().create(body=file_metadata, media_body=media, fields='id').execute()
        o_print(f'File ID: {file.get("id")}', opt=p)

        # Get the ID of the uploaded image file
        file_id = file.get('id')

        # Set the permissions on the file to allow anyone with the link to view it
        permission = {
            'type': 'anyone',
            'role': 'reader',
        }
        self.g_drive_s.permissions().create(fileId=file_id, body=permission).execute()

        # Retrieve the file's share URL
        file = self.g_drive_s.files().get(fileId=file_id, fields='webViewLink').execute()
        self.share_url = file.get('webViewLink')
        thumbnail_link = file.get('thumbnailLink')

        # Print the share URL
        o_print(f'Share URL:{self.share_url}', opt=p)
        return self.share_url

    def authenticate_google_chat(self,p=False):
        try:
            #credentials = SACredentials.from_service_account_file(self.service_account)
            service_account_info = self.cfg.image_params["service_account_post"]
            credentials = SACredentials.from_service_account_info(service_account_info)
            # Set up the Google| Chat API client
            chat = build('chat', 'v1', credentials=credentials)
        except:
            print("Google chat authentication failed. Check your service account credentials file ")
            raise
        else:
            o_print("Google chat authentication successful",opt=p)
            return chat

    def share_to_gchat(self, space_id, message_text=None,p=False):

       #check existence of authentication for google chat
        if self.g_chat_s is None:
            self.g_chat_s = self.authenticate_google_chat()
        if self.share_url is None:
            print("Google chat has no attachment, no message sent")
            return
        #preparing message
        if message_text == None:
            text_1 = f'Odkaz na google drive\n{self.share_url}'
        else:
            text_1 = f'{message_text}\nOdkaz na google drive:\n{self.share_url}'
        message_simple = {'text': text_1}
        try:
            self.g_chat_s.spaces().messages().create(parent=f'spaces/{space_id}', body=message_simple).execute()
            o_print('File shared successfully.',p)
        except:
            print(f'An error occurred while sending message', )
        else:
            o_print('Message sent.', p)

