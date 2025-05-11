import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load credentials from JSON file
GOOGLE_CREDENTIALS_FILE = "tinosolutions-invoices-d422558b4d05.json"  # Change to your actual JSON file name

# Set the Google Drive folder ID where images will be stored
GOOGLE_DRIVE_FOLDER_ID = "15ANbwh6M8c7eAp_o8vWToOHs-ObjdLP9"  # Change this to your folder ID
"""
def upload_to_drive(file_path, file_name, folder_id):
    """Uploads a file to Google Drive and returns the file URL."""
    credentials = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/drive.file"])
    service = build("drive", "v3", credentials=credentials)

    file_metadata = {
        "name": file_name,
        "parents": [folder_id]  # Use provided folder ID instead of hardcoded `GOOGLE_DRIVE_FOLDER_ID`
    }

    media = MediaFileUpload(file_path, mimetype="image/jpeg")

    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = uploaded_file.get("id")
    return f"https://drive.google.com/uc?id={file_id}"
"""
def upload_to_drive(file_path, file_name, folder_id):
    try:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
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
