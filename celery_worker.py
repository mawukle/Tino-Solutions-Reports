import os
from celery import Celery
from flask import Flask
from models import db, projects
from drive_uploader import folder_has_files  # Your existing method

# Flask app context
def make_celery():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{os.getenv('JAWSDB_USER')}:{os.getenv('JAWSDB_PASSWORD')}@{os.getenv('JAWSDB_HOST')}/{os.getenv('JAWSDB_DB')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    celery = Celery(
        app.import_name,
        broker=os.getenv('REDIS_URL'),  # Redis Cloud URL
        backend=os.getenv('REDIS_URL')
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

celery = make_celery()

@celery.task()
def update_folder_has_files(project_id, folder_id):
    try:
        has_files = folder_has_files(folder_id)
        project = db.session.query(projects).get(project_id)
        if project:
            project.folder_has_files = has_files
            db.session.commit()
    except Exception as e:
        print(f"Error checking folder {folder_id}: {e}")
