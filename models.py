from flask_sqlalchemy import SQLAlchemy

# Initialize the database
db = SQLAlchemy()

# Define the Client model to map to the Client_List table
class Client(db.Model):
    __tablename__ = 'Client_List'
    Client_Unique_ID = db.Column(db.Integer, primary_key=True)
    Client_Name = db.Column(db.String(100), nullable=False)
    Town = db.Column(db.String(100), nullable=False)
    City = db.Column(db.String(100), nullable=True)
    Phone_Number = db.Column(db.String(20), nullable=True)
    Client_Code = db.Column(db.String(50), nullable=True)
    Contact_Person = db.Column(db.String(100), nullable=True)
    email_address = db.Column(db.String(100), nullable=True)

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

# You can add more models as needed to match other tables
