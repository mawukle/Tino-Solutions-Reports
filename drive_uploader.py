import os
import json
import base64
import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Set the Google Drive folder ID where images will be stored
GOOGLE_DRIVE_FOLDER_ID = "15ANbwh6M8c7eAp_o8vWToOHs-ObjdLP9"  # Change this to your folder ID

def get_google_credentials():
    """Get Google credentials from environment variable"""
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS environment variable not set")

    # Decode from base64
    credentials_info = json.loads(base64.b64decode(creds_json).decode("utf-8"))
    return credentials_info

def upload_to_drive(file_path, file_name, folder_id):
    try:
        # Get credentials from environment variable
        credentials_info = get_google_credentials()
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)  # Reduce memory

        file_metadata = {
            "name": file_name,
            "parents": [folder_id]
        }

        media = MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)

        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logging.info(f"Uploaded {int(status.progress() * 100)}%")

        return f"https://drive.google.com/uc?id={response['id']}"

    except Exception as e:
        logging.error(f"Upload failed for {file_name}: {e}")
        raise
