import os
import ssl
import logging
import gc
from flask import Flask
from celery import Celery
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from models import db, projects
from drive_uploader import upload_to_drive
from googleapiclient.http import MediaIoBaseUpload
import io

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

# In celery_worker.py after creating the celery instance
celery.conf.update(
    worker_max_memory_per_child=200000,  # 200MB in KB
    worker_max_tasks_per_child=10,       # Restart after 10 tasks
    worker_concurrency=2,                # Only 2 concurrent tasks
    broker_pool_limit=1,                 # Reduce Redis connections
    worker_prefetch_multiplier=1         # Only prefetch 1 task per worker
)

# ---------- Google Drive Helper Functions ----------
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

def get_or_create_folder(service, parent_id, project_id, client_name, town, sales_person):
    """Get or create a folder, ensuring no duplicates"""
    try:
        # Clean inputs and create consistent folder name
        folder_name = f"{client_name.strip()}_{town.strip()}_{sales_person.strip()}_{project_id}"
        folder_name = "".join(c for c in folder_name if c not in r'\/:*?"<>|')  # Remove invalid chars

        # First check if the project already has a valid folder
        existing_project = db.session.query(projects).filter_by(project_id=project_id).first()
        if existing_project and existing_project.google_folder_id:
            # Verify the folder exists in Drive
            try:
                folder = service.files().get(
                    fileId=existing_project.google_folder_id,
                    fields='id'
                ).execute()
                return existing_project.google_folder_id  # Valid existing folder
            except:
                pass  # Folder doesn't exist, will create new one

        # Search for existing folder by name
        query = (
            f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        result = service.files().list(
            q=query,
            fields="files(id,name)",
            pageSize=1
        ).execute()

        if result.get('files'):
            return result['files'][0]['id']  # Return existing folder

        # Create new folder
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = service.files().create(
            body=folder_metadata,
            fields='id'
        ).execute()

        return folder.get('id')

    except Exception as e:
        logging.error(f"Error in get_or_create_folder: {e}")
        return None
# ---------- Celery Tasks ----------
@celery.task(bind=True)
def create_folder_if_needed(self, project_id, client_name, town, sales_person):
    logging.info(f"Starting folder creation task for project {project_id}")
    try:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=credentials)

        # Create or get folder
        folder_id = get_or_create_folder(service, "15ANbwh6M8c7eAp_o8vWToOHs-ObjdLP9", project_id, client_name, town, sales_person)

        # Update project with folder ID
        if folder_id:
            project = db.session.query(projects).filter_by(project_id=project_id).first()
            if project:
                project.google_folder_id = folder_id
                db.session.commit()
                logging.info(f"Folder created for project {project_id}: {folder_id}")
            else:
                logging.error(f"Project with ID {project_id} not found.")
        else:
            logging.error(f"Folder creation failed for project {project_id}")

    except Exception as e:
        logging.error(f"Error creating folder for project {project_id}: {e}")
    finally:
        gc.collect()

@celery.task(bind=True)
def update_folder_has_files(self, project_id, folder_id):
    try:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=credentials)

        has_files = folder_contains_files(service, folder_id)

        project = db.session.query(projects).filter_by(project_id=project_id).first()
        if project:
            project.folder_has_files = has_files
            db.session.commit()

    except Exception as e:
        logging.error(f"Error updating folder_has_files for project {project_id}: {e}")
    finally:
        gc.collect()


@celery.task(bind=True)
def upload_files_to_drive(self, folder_id, file_data):
    """Process file uploads to Google Drive using in-memory files"""
    try:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=credentials)

        for file_info in file_data:
            try:
                file_content = io.BytesIO(file_info['content'])
                file_metadata = {
                    'name': file_info['filename'],
                    'parents': [folder_id]
                }

                media = MediaIoBaseUpload(
                    file_content,
                    mimetype='application/octet-stream',
                    resumable=True
                )

                service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

                logging.info(f"Successfully uploaded {file_info['filename']}")

            except Exception as e:
                logging.error(f"Failed to upload {file_info['filename']}: {str(e)}")
                continue

    except Exception as e:
        logging.error(f"Drive service error: {str(e)}")
        raise self.retry(exc=e)


@celery.task(bind=True)
def create_missing_folders(self):
    try:
        self.update_state(state='STARTED')

        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=credentials)

        # Get projects missing folders
        projects_missing_folders = db.session.query(projects).filter(
            (projects.google_folder_id.is_(None)) |
            (projects.google_folder_id == '')
        ).all()

        created_count = 0

        for project in projects_missing_folders:
            try:
                if not all([project.client_name, project.town, project.sales_person]):
                    continue

                folder_id = get_or_create_folder(
                    service,
                    "15ANbwh6M8c7eAp_o8vWToOHs-ObjdLP9",
                    project.project_id,
                    project.client_name,
                    project.town,
                    project.sales_person
                )

                if folder_id:
                    project.google_folder_id = folder_id
                    db.session.commit()
                    created_count += 1
                    logging.info(f"Created folder for project {project.project_id}")

            except Exception as e:
                logging.error(f"Error processing project {project.project_id}: {e}")
                db.session.rollback()
                continue

        return {
            "status": "completed",
            "folders_created": created_count,
            "total_processed": len(projects_missing_folders)
        }

    except Exception as e:
        logging.error(f"Critical error in create_missing_folders: {e}", exc_info=True)
        raise self.retry(exc=e)

@celery.task(bind=True)
def rename_project_folder_task(self, project_id, client_name, town, sales_person):
    """Async task to rename a project folder in Google Drive"""
    try:
        credentials = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=credentials)

        # Get the project to ensure it still exists and has a folder ID
        with app.app_context():
            project = db.session.query(projects).filter_by(project_id=project_id).first()
            if not project or not project.google_folder_id:
                logging.warning(f"Project {project_id} not found or missing folder ID")
                return False

            # Generate the expected folder name
            expected_name = f"{client_name.strip()}_{town.strip()}_{sales_person.strip()}_{project_id}"
            expected_name = "".join(c for c in expected_name if c not in r'\/:*?"<>|')

            try:
                # Get current folder name from Google Drive
                folder = service.files().get(
                    fileId=project.google_folder_id,
                    fields="name"
                ).execute()

                current_name = folder.get('name', '')

                if current_name != expected_name:
                    # Update folder name if it doesn't match
                    service.files().update(
                        fileId=project.google_folder_id,
                        body={'name': expected_name}
                    ).execute()
                    logging.info(f"Renamed folder for project {project_id} to {expected_name}")
                    return True
                return False

            except Exception as e:
                logging.error(f"Error renaming folder for project {project_id}: {e}")
                raise self.retry(exc=e, countdown=60, max_retries=3)

    except Exception as e:
        logging.error(f"Critical error in rename_project_folder_task: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
