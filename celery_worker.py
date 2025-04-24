import os
import logging
from celery import Celery
from flask import Flask
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from models import db, projects

GOOGLE_CREDENTIALS_FILE = "tinosolutions-invoices-d422558b4d05.json"

# Flask app context
def make_celery():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{os.getenv('JAWSDB_USER')}:{os.getenv('JAWSDB_PASSWORD')}@{os.getenv('JAWSDB_HOST')}/{os.getenv('JAWSDB_DB')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    celery = Celery(
        app.import_name,
        broker=os.getenv('REDIS_URL'),
        backend=os.getenv('REDIS_URL')
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

celery = make_celery()

def folder_has_files(folder_id):
    """Check if the Google Drive folder contains any files."""
    try:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=credentials)

        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            pageSize=1,
            fields="files(id)"
        ).execute()

        files = response.get("files", [])
        return len(files) > 0

    except Exception as e:
        logging.error(f"Error checking folder {folder_id} contents: {e}")
        return False

@celery.task()
def update_folder_has_files(project_id, folder_id):
    try:
        has_files = folder_has_files(folder_id)
        project = db.session.query(projects).get(project_id)
        if project:
            project.folder_has_files = has_files
            db.session.commit()
    except Exception as e:
        logging.error(f"Error in update_folder_has_files task for project {project_id}: {e}")
