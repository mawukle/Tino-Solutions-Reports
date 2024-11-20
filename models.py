from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

# Initialize the database
db = SQLAlchemy()

# Define the Client model to map to the Client_List table
class Client_List(db.Model):
    __tablename__ = 'Client_List'
    Client_Unique_ID = db.Column(db.Integer, primary_key=True)
    Client_Name = db.Column(db.String(100), nullable=False)
    Town = db.Column(db.String(100), nullable=False)
    City = db.Column(db.String(100), nullable=True)
    Phone_Number = db.Column(db.String(20), nullable=True)
    Client_Code = db.Column(db.String(50), nullable=True)
    Contact_Person = db.Column(db.String(100), nullable=True)
    email_address = db.Column(db.String(100), nullable=True)

    jobs = relationship('Job_Tracking', backref='client', lazy=True)

# Define the updated Items model to map to the Items_List table
class Item(db.Model):
    __tablename__ = 'Items_List'
    Item_ID = db.Column(db.Integer, primary_key=True)
    Quantity = db.Column(db.Integer, nullable=True)  # Newly added column
    Item_Description = db.Column(db.String(255), nullable=False)
    kVA_kW = db.Column(db.String(50), nullable=True)  # Newly added column
    Voltage = db.Column(db.String(50), nullable=True)  # Newly added column
    Brand = db.Column(db.String(50), nullable=True)  # Newly added column
    Phase = db.Column(db.String(50), nullable=True)  # Newly added column
    kWh = db.Column(db.Float, nullable=True)  # Newly added column
    Ah = db.Column(db.Float, nullable=True)  # Newly added column
    Component = db.Column(db.String(255), nullable=True)  # Newly added column

# Define the Team Members model
class Team_Members(db.Model):
    __tablename__ = 'Team_Members'
    Team_Member_ID = db.Column(db.Integer, primary_key=True)
    Team_Member_Name = db.Column(db.String(255), nullable=False)

    # Relationships
    job_teams = relationship('job_team_members', backref='team_member', lazy=True)
    assigned_jobs = relationship('Team_Members_Assigned', backref='assigned_member', lazy=True)

# Define the Job Tracking model
class Job_Tracking(db.Model):
    __tablename__ = 'Job_Tracking'
    Job_ID = db.Column(db.Integer, primary_key=True)
    Client_Unique_ID = db.Column(db.Integer, db.ForeignKey('Client_List.Client_Unique_ID'), nullable=False)
    Client_Name = db.Column(db.String(255))
    Town = db.Column(db.String(255))
    Phone_Number = db.Column(db.String(20))
    Date = db.Column(db.Date, nullable=False)
    Tasks_Performed = db.Column(db.Text, nullable=True)
    Any_Issues = db.Column(db.Text, nullable=True)
    Percentage_Completion = db.Column(db.Float, nullable=True)

    # Relationships
    team_members = relationship('job_team_members', backref='job_tracking', lazy=True)
    pictures = relationship('Job_Pictures', backref='job_tracking', lazy=True)

# Define the job_team_members model
class job_team_members(db.Model):
    __tablename__ = 'job_team_members'
    Job_Team_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Job_ID = db.Column(db.Integer, db.ForeignKey('Job_Tracking.Job_ID'), nullable=False)
    Team_Member_ID = db.Column(db.Integer, db.ForeignKey('Team_Members.Team_Member_ID'), nullable=False)

# Define the Team_Members_Assigned model
class Team_Members_Assigned(db.Model):
    __tablename__ = 'Team_Members_Assigned'
    Assignment_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Job_ID = db.Column(db.Integer, db.ForeignKey('Job_Tracking.Job_ID'), nullable=False)
    Team_Member_ID = db.Column(db.Integer, db.ForeignKey('Team_Members.Team_Member_ID'), nullable=False)

# Define the Job Pictures model
class Job_Pictures(db.Model):
    __tablename__ = 'Job_Pictures'
    Picture_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Job_ID = db.Column(db.Integer, db.ForeignKey('Job_Tracking.Job_ID'), nullable=False)
    Picture_URL = db.Column(db.String(255), nullable=True)

# Define the Assigned Teams model
class Assigned_Teams(db.Model):
    __tablename__ = 'Assigned_Teams'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_name = db.Column(db.String(255), nullable=False)
    assigned_team = db.Column(db.String(255), nullable=False)
    assignment_date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
"""
class Client_Items(db.Model):
    __tablename__ = 'client_items'
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    component = db.Column(db.String(255), nullable=False)
    item_description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
"""
class ClientItems(db.Model):
    __tablename__ = 'client_items'

    client_item_id = db.Column(db.Integer, primary_key=True)  # Rename the primary key column to 'client_item_id'
    client_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    component = db.Column(db.String(255), nullable=False)
    item_description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<ClientItem {self.client_item_id}, {self.client_name}, {self.date}>"
