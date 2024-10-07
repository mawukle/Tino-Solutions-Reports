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

# Define the Items model to map to the Items_List table
class Item(db.Model):
    __tablename__ = 'Items_List'
    Item_ID = db.Column(db.Integer, primary_key=True)
    Item_Description = db.Column(db.String(255), nullable=False)
    Retail_Price_With_Tax = db.Column(db.Float, nullable=True)
    Super_Dealer_Price_With_Tax = db.Column(db.Float, nullable=True)
    End_User_USD = db.Column(db.Float, nullable=True)
    End_User_GHC = db.Column(db.Float, nullable=True)
    Super_Dealer_USD = db.Column(db.Float, nullable=True)
    Super_Dealer_GHC = db.Column(db.Float, nullable=True)

# Define the Team Members model
class Team_Members(db.Model):
    __tablename__ = 'Team_Members'
    Team_Member_ID = db.Column(db.Integer, primary_key=True)
    Team_Member_Name = db.Column(db.String(255), nullable=False)

    # Adjusting backref names to prevent conflicts
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

    # Adjusting backrefs
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
