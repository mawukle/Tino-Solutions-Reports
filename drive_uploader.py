import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load credentials from JSON file
GOOGLE_CREDENTIALS_FILE = "tinosolutions-invoices-d422558b4d05.json"  # Change to your actual JSON file name

# Set the Google Drive folder ID where images will be stored
GOOGLE_DRIVE_FOLDER_ID = "15ANbwh6M8c7eAp_o8vWToOHs-ObjdLP9"  # Change this to your folder ID

def upload_to_drive(file_path, file_name, folder_id=None):
    """Uploads a file to Google Drive and returns the file URL."""
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    service = build("drive", "v3", credentials=credentials)

    file_metadata = {"name": file_name}

    # If folder_id is provided, store in that folder, otherwise leave in root
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(file_path, mimetype="image/jpeg")

    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = uploaded_file.get("id")
    return f"https://drive.google.com/uc?id={file_id}"
