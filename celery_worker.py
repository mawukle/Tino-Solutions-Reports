import os
import ssl
import logging
import gc
from flask import Flask
from celery import Celery
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from models import db, projects

GOOGLE_CREDENTIALS_FILE = "tinosolutions-invoices-d422558b4d05.json"

def make_celery():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{os.getenv('JAWSDB_USER')}:{os.getenv('JAWSDB_PASSWORD')}@{os.getenv('JAWSDB_HOST')}/{os.getenv('JAWSDB_DB')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        logging.error("REDIS_URL environment variable is not set.")
        raise RuntimeError("REDIS_URL environment variable is required but not found.")

    broker_use_ssl = redis_backend_use_ssl = None
    if redis_url.startswith('rediss://'):
        ssl_config = {'ssl_cert_reqs': ssl.CERT_NONE}
        broker_use_ssl = ssl_config
        redis_backend_use_ssl = ssl_config
    elif not redis_url.startswith('redis://'):
        raise RuntimeError("Unsupported Redis URL scheme.")

    celery = Celery(
        app.import_name,
        broker=redis_url,
        backend=redis_url,
        broker_use_ssl=broker_use_ssl,
        redis_backend_use_ssl=redis_backend_use_ssl
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

celery = make_celery()

def folder_contains_files(service, folder_id):
    try:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            pageSize=1,
            fields="files(id)"
        ).execute()
        return bool(response.get("files"))
    except Exception as e:
        logging.error(f"Error checking folder contents for folder_id={folder_id}: {e}")
        return False

@celery.task(bind=True)
def update_folder_has_files(self, project_id, folder_id):
    try:
        # Setup Drive API
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=credentials)

        # Check folder contents
        has_files = folder_contains_files(service, folder_id)

        # Update DB
        project = db.session.query(projects).filter_by(project_id=project_id).first()
        if project:
            project.folder_has_files = has_files
            db.session.commit()

    except Exception as e:
        logging.error(f"Error updating folder_has_files for project {project_id}: {e}")

    finally:
        # Memory cleanup
        gc.collect()
