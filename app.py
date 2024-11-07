from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_from_directory, abort
import os
import logging
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import pymysql
from models import db, Client_List, Item, Team_Members, Assigned_Teams, job_team_members, Job_Pictures, Team_Members_Assigned, Job_Tracking  # Import db only once from models
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
#from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Float, and_, func, literal_column, desc, select, distinct, create_engine, case
from sqlalchemy.orm import sessionmaker, aliased
import pandas as pd
from sqlalchemy import text
from datetime import datetime, timedelta
#from datetime import datetime

pymysql.install_as_MySQLdb()

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set to INFO for production
#logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__, static_folder='static')

# Use an environment variable for the secret key
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key')  # Default value for local development

# Define UPLOAD_FOLDER
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')

# Create the upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER  # Correctly reference the upload folder
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit upload size to 16 MB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}

# Database configuration from environment variables
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{os.getenv('JAWSDB_USER')}:{os.getenv('JAWSDB_PASSWORD')}@{os.getenv('JAWSDB_HOST')}/{os.getenv('JAWSDB_DB')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable track modifications for performance

# Initialize the database and migration tools
# db = SQLAlchemy(app)  # This line has been removed to prevent multiple initializations
migrate = Migrate(app, db)

# Initialize the SQLAlchemy object with the app context
db.init_app(app)

# Check if environment variables are set
if not all([os.getenv('JAWSDB_HOST'), os.getenv('JAWSDB_USER'), os.getenv('JAWSDB_PASSWORD'), os.getenv('JAWSDB_DB')]):
    logging.error("One or more JAWSDB environment variables are not set")
    raise EnvironmentError("Database environment variables are not set")

@app.route('/test_db')
def test_db():
    connection = get_sql_connection()
    if connection:
        return "Connection successful"
    return "Connection failed"

# Error handling
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# Function to establish the connection to the database
def get_sql_connection():
    try:
        connection = pymysql.connect(
            host=os.getenv('JAWSDB_HOST','localhost'),
            user=os.getenv('JAWSDB_USER', 'root'),
            password=os.getenv('JAWSDB_PASSWORD', ''),
            database=os.getenv('JAWSDB_DB', ''),
            cursorclass=pymysql.cursors.DictCursor
        )
        logging.info("Database connection successful")
        return connection
    except pymysql.MySQLError as e:
        logging.error(f"Database connection failed: {e}")
        return None  # Return None to allow error handling in calling code

# Function to check if a record already exists
#import logging

# Function to check if a record already exists
def record_exists(cursor, client_name, town, city):
    query = """
    SELECT COUNT(*) FROM Client_List WHERE
    Client_Name = %s AND Town = %s AND City = %s
    """
    cursor.execute(query, (client_name, town, city))

    # Fetch the result
    result = cursor.fetchone()

    # Check if the query result exists and return based on 'COUNT(*)'
    if result and result.get('COUNT(*)', 0) > 0:
        return True
    else:
        return False


# Function to delete duplicate records
def delete_duplicates():
    connection = get_sql_connection()
    if connection:
        cursor = connection.cursor()
        try:
            # This query deletes all but the first occurrence of each duplicate based on Client_Name, Town, and City
            delete_query = """
            DELETE t1 FROM Client_List t1
            INNER JOIN Client_List t2
            WHERE
                t1.Client_Unique_ID > t2.Client_Unique_ID AND
                t1.Client_Name = t2.Client_Name AND
                t1.Town = t2.Town AND
                t1.City = t2.City;
            """
            cursor.execute(delete_query)
            connection.commit()
            print("Duplicates deleted successfully.")
        except mysql.connector.Error as err:
            print(f"Error deleting duplicates: {err}")
        finally:
            cursor.close()
            connection.close()

# Function to delete empty rows from the database
def delete_empty_rows():
    connection = get_sql_connection()
    if connection:
        cursor = connection.cursor()
        try:
            # Query to delete rows where critical columns are empty
            delete_query = """
            DELETE FROM Client_List
            WHERE Client_Name IS NULL OR Client_Name = '' OR
                  Town IS NULL OR Town = '' OR
                  City IS NULL OR City = ''
            """
            cursor.execute(delete_query)
            connection.commit()
            print("Empty rows deleted successfully.")
        except mysql.connector.Error as err:
            print(f"Error deleting empty rows: {err}")
        finally:
            cursor.close()
            connection.close()
@app.route('/', methods=['GET', 'POST'])
def home():
    return render_template('index.html')

@app.route('/index', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@app.route('/invoice_sheet', methods=['GET','POST'])
def invoice_sheet():
    selected_items = []

    if request.method == 'POST':
        # Get the list of selected item IDs from the form
        selected_ids = request.form.getlist('selected_items[]')

        if selected_ids:
            # Fetch details for selected IDs from the database
            selected_items = get_items_by_ids(selected_ids)
        else:
            flash('No items were selected. Please select items to display.', 'warning')

    # Render the invoice_sheet.html with the selected items
    return render_template('invoice_sheet.html', selected_items=selected_items)


@app.route('/team_ranking', methods=['GET', 'POST'])
def team_ranking():
    try:
        if request.method == 'POST':
            # Get the date range from the form
            start_date = request.form['start_date']
            end_date = request.form['end_date']

            # CTE for unique days each client was visited
            client_unique_days_query = db.session.query(
                Job_Tracking.Client_Unique_ID,
                func.count(func.distinct(Job_Tracking.Date)).label('unique_days_at_client')
            ).filter(Job_Tracking.Date.between(start_date, end_date)) \
             .group_by(Job_Tracking.Client_Unique_ID).cte("client_unique_days")

            # CTE for total unique days each team member spent at clients
            team_member_total_days_query = db.session.query(
                Team_Members.Team_Member_Name,
                func.sum(func.distinct(client_unique_days_query.c.unique_days_at_client).label('total_days_at_clients')
            ).select_from(
                Team_Members
            ).join(
                job_team_members, job_team_members.Team_Member_ID == Team_Members.Team_Member_ID
            ).join(
                Job_Tracking, Job_Tracking.Job_ID == job_team_members.Job_ID
            ).join(
                client_unique_days_query, Job_Tracking.Client_Unique_ID == client_unique_days_query.c.Client_Unique_ID
            ).filter(
                Job_Tracking.Date.between(start_date, end_date)
            ).group_by(
                Team_Members.Team_Member_Name
            )).cte("team_member_total_days")

            # CTE for days worked by each team member
            days_worked_query = db.session.query(
                Team_Members.Team_Member_Name,
                func.count(func.distinct(Job_Tracking.Date)).label('days_worked')
            ).join(job_team_members, job_team_members.Team_Member_ID == Team_Members.Team_Member_ID) \
             .join(Job_Tracking, Job_Tracking.Job_ID == job_team_members.Job_ID) \
             .filter(Job_Tracking.Date.between(start_date, end_date)) \
             .group_by(Team_Members.Team_Member_Name).cte("days_worked")

            # CTE for clients visited by each team member
            clients_visited_query = db.session.query(
                Team_Members.Team_Member_Name,
                func.count(func.distinct(Job_Tracking.Client_Unique_ID)).label('clients_visited')
            ).join(job_team_members, job_team_members.Team_Member_ID == Team_Members.Team_Member_ID) \
             .join(Job_Tracking, Job_Tracking.Job_ID == job_team_members.Job_ID) \
             .filter(Job_Tracking.Date.between(start_date, end_date)) \
             .group_by(Team_Members.Team_Member_Name).cte("clients_visited")

            # Final ranking query with calculation
            ranking_query = db.session.query(
                Team_Members.Team_Member_Name,
                days_worked_query.c.days_worked,
                clients_visited_query.c.clients_visited,
                team_member_total_days_query.c.total_days_at_clients,
                (days_worked_query.c.days_worked +
                 func.coalesce(clients_visited_query.c.clients_visited, 0) /
                 func.coalesce(team_member_total_days_query.c.total_days_at_clients, 1)
                ).label('ranking_score')
            ).join(days_worked_query, days_worked_query.c.Team_Member_Name == Team_Members.Team_Member_Name) \
             .join(clients_visited_query, clients_visited_query.c.Team_Member_Name == Team_Members.Team_Member_Name) \
             .outerjoin(team_member_total_days_query, team_member_total_days_query.c.Team_Member_Name == Team_Members.Team_Member_Name) \
             .order_by(desc('ranking_score'))

            # Fetch the rankings
            team_rankings = ranking_query.all()

            return render_template('team_ranking.html', team_rankings=team_rankings)

        return render_template('team_ranking.html')

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error occurred in team_ranking: {e}")
        return str(e)

    finally:
        db.session.close()










'''
@app.route('/item_list', methods=['GET', 'POST'])
def item_list():
    return render_template('item_list.html')

@app.route('/newItem_entryForm', methods=['GET', 'POST'])
def newItem_entryForm():
    return render_template('newItem_entryForm.html')
'''
# Route for the newItem_entryForm that displays the form and handles Excel file uploads
@app.route('/newItem_entryForm', methods=['GET', 'POST'])
def newItem_entryForm():
    message = ''
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            # Handle file upload
            file = request.files['file']
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)

            try:
                df = pd.read_excel(file_path)
                df = df.astype(str)  # Convert all columns to string
                df.replace('nan', '', inplace=True)  # Replace 'nan' strings with empty strings
            except Exception as e:
                message = f"Error reading file: {e}"
                return render_template('index.html', message=message)

            connection = get_sql_connection()
            if connection:
                cursor = connection.cursor()
                rows_processed = 0
                for _, row in df.iterrows():
                    # Skip rows where Item_Description is blank
                    if row['Item_Description'].strip() == '':
                        continue

                    item_description = row.get('Item_Description')
                    retail_price_with_tax = row.get('Retail_Price_With_Tax')
                    super_dealer_price_with_tax = row.get('Super_Dealer_Price_With_Tax')
                    end_user_usd = row.get('End_User_USD')
                    end_user_ghc = row.get('End_User_GHC')
                    super_dealer_usd = row.get('Super_Dealer_USD')
                    super_dealer_ghc = row.get('Super_Dealer_GHC')

                    # Remove old entries with the same Item_Description
                    cursor.execute("DELETE FROM Items_List WHERE Item_Description = %s", (item_description,))

                    # Insert new row
                    insert_query = """
                    INSERT INTO Items_List (Item_Description, Retail_Price_With_Tax, Super_Dealer_Price_With_Tax,
                                            End_User_USD, End_User_GHC, Super_Dealer_USD, Super_Dealer_GHC)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """
                    try:
                        cursor.execute(insert_query, (
                            item_description, retail_price_with_tax, super_dealer_price_with_tax,
                            end_user_usd, end_user_ghc, super_dealer_usd, super_dealer_ghc
                        ))
                        rows_processed += 1
                    except mysql.connector.Error as err:
                        print(f"Database error: {err}")

                connection.commit()
                cursor.close()
                connection.close()
                os.remove(file_path)

                if rows_processed > 0:
                    message = f"File uploaded and {rows_processed} records processed successfully. Old duplicates removed."
                else:
                    message = "File uploaded but no new records were processed."
            else:
                message = 'Database connection failed'

        else:
            # Handle form submission
            item_description = request.form.get('item_description')
            retail_price_with_tax = request.form.get('retail_price_with_tax')
            super_dealer_price_with_tax = request.form.get('super_dealer_price_with_tax')
            end_user_usd = request.form.get('end_user_usd')
            end_user_ghc = request.form.get('end_user_ghc')
            super_dealer_usd = request.form.get('super_dealer_usd')
            super_dealer_ghc = request.form.get('super_dealer_ghc')

            connection = get_sql_connection()
            if connection:
                cursor = connection.cursor()
                # Remove old entries with the same Item_Description
                cursor.execute("DELETE FROM Items_List WHERE Item_Description = %s", (item_description,))

                # Insert new row
                insert_query = """
                INSERT INTO Items_List (Item_Description, Retail_Price_With_Tax, Super_Dealer_Price_With_Tax,
                                        End_User_USD, End_User_GHC, Super_Dealer_USD, Super_Dealer_GHC)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """
                try:
                    cursor.execute(insert_query, (
                        item_description, retail_price_with_tax, super_dealer_price_with_tax,
                        end_user_usd, end_user_ghc, super_dealer_usd, super_dealer_ghc
                    ))
                    connection.commit()

                    message = "Item added successfully. Old duplicates removed."
                except mysql.connector.Error as err:
                    print(f"Database error: {err}")
                    message = "Database error occurred."
                finally:
                    cursor.close()
                    connection.close()
            else:
                message = 'Database connection failed'

    return render_template('newItem_entryForm.html', message=message)

# Route for the newClient_entryForm that displays the form and handles Excel file uploads
@app.route('/newClient_entryForm', methods=['GET', 'POST'])
def newClient_entryForm():
    message = ''
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)

            try:
                df = pd.read_excel(file_path)
                df = df.astype(str)  # Convert all columns to string
                df.replace('nan', '', inplace=True)  # Replace 'nan' strings with empty strings
            except Exception as e:
                message = f"Error reading file: {e}"
                return render_template('index.html', message=message)

            connection = get_sql_connection()
            if connection:
                cursor = connection.cursor()
                insert_query = """
                INSERT INTO Client_List (Client_Name, Town, City, Phone_Number, Client_Code, Contact_Person, email_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                rows_inserted = 0
                for _, row in df.iterrows():
                    # Skip rows where critical fields are blank
                    if not row[['Client_Name', 'Town', 'City']].apply(lambda x: x.strip() != '').all():
                        continue

                    row_values = (
                        row.get('Client_Name'), row.get('Town'), row.get('City'),
                        row.get('Phone_Number'), row.get('Client_Code'),
                        row.get('Contact_Person'), row.get('email_address')
                    )
                    if not record_exists(cursor, row['Client_Name'], row['Town'], row['City']):
                        try:
                            cursor.execute(insert_query, row_values)
                            rows_inserted += 1
                        except mysql.connector.Error as err:
                            print(f"Database error: {err}")
                connection.commit()
                cursor.close()
                connection.close()
                os.remove(file_path)

                if rows_inserted > 0:
                    delete_duplicates()
                    delete_empty_rows()  # Call to delete empty rows
                    message = f"File uploaded and {rows_inserted} records inserted successfully. Duplicates and empty rows removed."
                else:
                    message = "File uploaded but no new records were inserted."
            else:
                message = 'Database connection failed'

        else:
            client_name = request.form.get('client_name')
            town = request.form.get('town')
            city = request.form.get('city')
            phone_number = request.form.get('phone_number')
            client_code = request.form.get('client_code')
            contact_person = request.form.get('contact_person')
            email_address = request.form.get('email_address')

            connection = get_sql_connection()
            if connection:
                cursor = connection.cursor()
                if not record_exists(cursor, client_name, town, city):
                    row_values = (client_name, town, city, phone_number, client_code, contact_person, email_address)
                    insert_query = """
                    INSERT INTO Client_List (Client_Name, Town, City, Phone_Number, Client_Code, Contact_Person, email_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    try:
                        cursor.execute(insert_query, row_values)
                        connection.commit()
                        delete_duplicates()
                        delete_empty_rows()  # Call to delete empty rows
                        message = "Client added successfully. Duplicates and empty rows removed."
                    except mysql.connector.Error as err:
                        print(f"Database error: {err}")
                        message = "Database error occurred."
                    finally:
                        cursor.close()
                        connection.close()
                else:
                    message = "Duplicate record detected. No new records inserted."

            else:
                message = 'Database connection failed'

    return render_template('newClient_entryForm.html', message=message)
"""
# Define the Client model
class Client(db.Model):
    __tablename__ = 'Client_List'
    Client_Unique_ID = db.Column(db.Integer, primary_key=True)
    Client_Name = db.Column(db.String(100))
    Town = db.Column(db.String(100))
    City = db.Column(db.String(100))
    Phone_Number = db.Column(db.String(20))
    Client_Code = db.Column(db.String(20))
    Contact_Person = db.Column(db.String(100))
    email_address = db.Column(db.String(100))
"""

# Route for displaying the client list sorted by Client_Unique_ID
@app.route('/client_list', methods=['GET'])
def client_list():
    message = request.args.get('message', '')  # Retrieve the message from query params if available

    try:
        # Query the clients sorted by Client_Unique_ID using SQLAlchemy
        clients = Client_List.query.order_by(Client_List.Client_Unique_ID).all()

        # Convert None values to empty strings and prepare the data for rendering
        clients = [[
            client.Client_Unique_ID,
            client.Client_Name or '',
            client.Town or '',
            client.City or '',
            client.Phone_Number or '',
            client.Client_Code or '',
            client.Contact_Person or '',
            client.email_address or ''
        ] for client in clients]

    except Exception as e:
        logging.error(f"Error fetching clients: {e}")
        message = 'Database query failed'
        clients = []

    return render_template('client_list.html', clients=clients, message=message)


"""
# Route for displaying the client list sorted by Client_Unique_ID
@app.route('/client_list', methods=['GET'])
def client_list():
    connection = get_sql_connection()
    clients = []
    message = request.args.get('message', '')  # Retrieve the message from query params if available
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT Client_Unique_ID, Client_Name, Town, City, Phone_Number, Client_Code, Contact_Person, email_address FROM Client_List ORDER BY Client_Unique_ID")
        clients = cursor.fetchall()
        #logging.debug(f"Clients fetched: {clients}")  # Log the fetched data
        # Process the data to replace None with empty strings
        clients = [[(value if value is not None else '') for value in row] for row in clients]
        cursor.close()
        connection.close()
    else:
        message = 'Database connection failed'

    return render_template('client_list.html', clients=clients, message=message)
"""

@app.route('/update_client', methods=['POST'])
def update_client():
    message = ''  # Initialize an empty message string

    # Get the form data
    client_ids = request.form.getlist('client_ids')
    client_names = request.form.getlist('client_names')
    towns = request.form.getlist('towns')
    cities = request.form.getlist('cities')
    phone_numbers = request.form.getlist('phone_numbers')
    client_codes = request.form.getlist('client_codes')
    contact_persons = request.form.getlist('contact_persons')
    email_addresses = request.form.getlist('email_addresses')

    for i in range(len(client_ids)):
        # Skip rows with blank required values
        if any(field.strip() == '' for field in [client_names[i], towns[i], cities[i]]):
            continue

        try:
            # Fetch the client by ID
            client = Client_List.query.get(client_ids[i])

            if client:
                # Update the client fields
                Client_List.Client_Name = client_names[i]
                Client_List.Town = towns[i]
                Client_List.City = cities[i]
                Client_List.Phone_Number = phone_numbers[i]
                Client_List.Client_Code = client_codes[i]
                Client_List.Contact_Person = contact_persons[i]
                Client_List.email_address = email_addresses[i]

                # Commit the changes to the database
                db.session.commit()
            else:
                message += f"Client with ID {client_ids[i]} not found.<br>"

        except IntegrityError as e:
            db.session.rollback()  # Rollback the transaction in case of errors
            print(f"Duplicate entry error: {e}")
            message += f"Duplicate entry detected for Client Name: '{client_names[i]}', Town: '{towns[i]}', City: '{cities[i]}'.<br>"

    if message:
        message = 'Some updates failed due to errors.<br>' + message

    return redirect(url_for('client_list', message=message))

"""
@app.route('/update_client', methods=['POST'])
def update_client():
    connection = get_sql_connection()
    message = ''  # Initialize an empty message string

    if connection:
        cursor = connection.cursor()
        client_ids = request.form.getlist('client_ids')
        client_names = request.form.getlist('client_names')
        towns = request.form.getlist('towns')
        cities = request.form.getlist('cities')
        phone_numbers = request.form.getlist('phone_numbers')
        client_codes = request.form.getlist('client_codes')
        contact_persons = request.form.getlist('contact_persons')
        email_addresses = request.form.getlist('email_addresses')
"""
#        update_query = """
#        UPDATE Client_List
#        SET Client_Name = %s, Town = %s, City = %s, Phone_Number = %s, Client_Code = %s, Contact_Person = %s, email_address = %s
#        WHERE Client_Unique_ID = %s
#        """
"""
        for i in range(len(client_ids)):
            # Skip rows with blank values
            if any(field.strip() == '' for field in [client_names[i], towns[i], cities[i]]):
                continue

            try:
                cursor.execute(update_query, (
                    client_names[i], towns[i], cities[i], phone_numbers[i],
                    client_codes[i], contact_persons[i], email_addresses[i],
                    client_ids[i]
                ))
            except mysql.connector.errors.IntegrityError as e:
                print(f"Duplicate entry error: {e}")
                message += f"Duplicate entry detected for Client Name: '{client_names[i]}', Town: '{towns[i]}', City: '{cities[i]}'.<br>"

        connection.commit()
        cursor.close()
        connection.close()

        if message:
            message = 'Some updates failed due to duplicate entries.<br>' + message

    else:
        message = 'Database connection failed'

    return redirect(url_for('client_list', message=message))
"""

@app.route('/delete_client/<client_id>', methods=['POST'])
def delete_client(client_id):
    try:
        # Find the client by ID
        client = Client_List.query.get(client_id)

        if client:
            # Delete the client
            db.session.delete(client)
            db.session.commit()
            message = 'Client deleted successfully.'
        else:
            message = 'Client not found.'

    except SQLAlchemyError as err:
        # Rollback the transaction in case of an error
        db.session.rollback()
        print(f"Database error: {err}")
        message = 'Error deleting Client_List.'

    return redirect(url_for('client_list', message=message))

"""
@app.route('/delete_client/<client_id>', methods=['POST'])
def delete_client(client_id):
    connection = get_sql_connection()
    if connection:
        cursor = connection.cursor()
        try:
            cursor.execute("DELETE FROM Client_List WHERE Client_Unique_ID = %s", (client_id,))
            connection.commit()
            message = 'Client deleted successfully.'
        except mysql.connector.Error as err:
            print(f"Database error: {err}")
            message = 'Error deleting Client_List.'
        finally:
            cursor.close()
            connection.close()
    else:
        message = 'Database connection failed'

    return redirect(url_for('client_list', message=message))
"""

"""
class Item(db.Model):
    __tablename__ = 'Items_List'
    Item_ID = Column(Integer, primary_key=True)
    Item_Description = Column(String(255))
    Retail_Price_With_Tax = Column(Float)
    Super_Dealer_Price_With_Tax = Column(Float)
    End_User_USD = Column(Float)
    End_User_GHC = Column(Float)
    Super_Dealer_USD = Column(Float)
    Super_Dealer_GHC = Column(Float)
"""

@app.route('/item_list', methods=['GET', 'POST'])
def item_list():
    if request.method == 'POST':
        # Handle file upload
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            try:
                # Read the Excel file using pandas
                data = pd.read_excel(filepath)
                # Replace NaN values with None
                data = data.where(pd.notnull(data), None)

                # Insert data into the database using SQLAlchemy
                for index, row in data.iterrows():
                    try:
                        # Create an Item object for each row
                        item = Item(
                            Item_ID=row['Item_ID'],
                            Item_Description=row['Item_Description'],
                            Retail_Price_With_Tax=row['Retail_Price_With_Tax'],
                            Super_Dealer_Price_With_Tax=row['Super_Dealer_Price_With_Tax'],
                            End_User_USD=row['End_User_USD'],
                            End_User_GHC=row['End_User_GHC'],
                            Super_Dealer_USD=row['Super_Dealer_USD'],
                            Super_Dealer_GHC=row['Super_Dealer_GHC']
                        )
                        # Add the item to the session
                        db.session.add(item)
                    except SQLAlchemyError as e:
                        flash(f"Error processing row {index + 1}: {str(e)}")

                # Commit the transaction to insert the rows
                db.session.commit()
                flash('File successfully uploaded and data inserted into the database.')
            except Exception as e:
                flash(f"Error processing file: {str(e)}")
            finally:
                os.remove(filepath)  # Clean up the uploaded file

            return redirect(url_for('newItem_entryForm'))

    # Fetch data from the Items_List table
    try:
        # Retrieve all items from the database using SQLAlchemy
        items = Item.query.all()
    except SQLAlchemyError as e:
        items = []
        flash(f"Error fetching items: {str(e)}")

    return render_template('item_list.html', items=items)

"""
@app.route('/item_list', methods=['GET', 'POST'])
def item_list():
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            try:
                # Read the Excel file using pandas
                data = pd.read_excel(filepath)
                # Replace NaN values with None
                data = data.where(pd.notnull(data), None)

                # Insert data into MySQL table
                connection = get_sql_connection()
                if connection:
                    cursor = connection.cursor()
                    # Loop through DataFrame rows and insert data into MySQL table
                    for index, row in data.iterrows():
                        try:
"""
#                            cursor.execute("""
#                                INSERT INTO Items_List (Item_ID, Item_Description, Retail_Price_With_Tax, Super_Dealer_Price_With_Tax, End_User_USD, End_User_GHC, Super_Dealer_USD, Super_Dealer_GHC)
#                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
#                            """, (
"""
                                row['Item_ID'], row['Item_Description'], row['Retail_Price_With_Tax'], row['Super_Dealer_Price_With_Tax'],
                                row['End_User_USD'], row['End_User_GHC'], row['Super_Dealer_USD'], row['Super_Dealer_GHC']
                            ))
                            connection.commit()
                        except Exception as e:
                            flash(f"Error processing row {index + 1}: {e}")
                    flash('File successfully uploaded and data inserted into the database.')
                else:
                    flash('Database connection failed.')
            except Exception as e:
                flash(f"Error processing file: {e}")
            finally:
                if connection and connection.is_connected():
                    cursor.close()
                    connection.close()
                os.remove(filepath)  # Clean up the uploaded file

            return redirect(url_for('newItem_entryForm'))

    # Fetch data from the Items_List table
    try:
        connection = get_sql_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("SELECT Item_ID, Item_Description, Retail_Price_With_Tax, Super_Dealer_Price_With_Tax, End_User_USD, End_User_GHC, Super_Dealer_USD, Super_Dealer_GHC FROM Items_List")
            items = cursor.fetchall()  # Fetch all rows from the executed query

            # Debugging: Print items to console to check if data is fetched correctly
            #print("Fetched Items:", items)
        else:
            items = []
            flash('Database connection failed.')
    except Exception as e:
        items = []
        flash(f"Error fetching items: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

    return render_template('item_list.html', items=items)
"""
@app.route('/update_item', methods=['POST'])
def update_item():
    connection = get_sql_connection()
    message = ''  # Initialize an empty message string

    if connection:
        cursor = connection.cursor()

        # Extracting individual form values
        item_id = request.form.get('item_id')
        item_description = request.form.get('item_description')
        retail_price_with_tax = request.form.get('retail_price_with_tax')
        super_dealer_price_with_tax = request.form.get('super_dealer_price_with_tax')
        end_user_usd = request.form.get('end_user_usd')
        end_user_ghc = request.form.get('end_user_ghc')
        super_dealer_usd = request.form.get('super_dealer_usd')
        super_dealer_ghc = request.form.get('super_dealer_ghc')

        if item_id and item_description and retail_price_with_tax and super_dealer_price_with_tax:
            try:
                # Update a single item
                cursor.execute("""
                    UPDATE Items_List
                    SET Item_Description = %s, Retail_Price_With_Tax = %s, Super_Dealer_Price_With_Tax = %s,
                        End_User_USD = %s, End_User_GHC = %s, Super_Dealer_USD = %s, Super_Dealer_GHC = %s
                    WHERE Item_ID = %s
                """, (item_description, retail_price_with_tax, super_dealer_price_with_tax,
                      end_user_usd, end_user_ghc, super_dealer_usd, super_dealer_ghc, item_id))
                connection.commit()
                flash('Item updated successfully.')
            except Exception as e:
                flash(f'Error updating item: {e}')
        else:
            # Handle batch update if individual values are not found
            item_ids = request.form.getlist('item_ids')
            item_descriptions = request.form.getlist('item_descriptions')
            retail_prices_with_tax = request.form.getlist('retail_prices_with_tax')
            super_dealer_prices_with_tax = request.form.getlist('super_dealer_prices_with_tax')
            end_user_usds = request.form.getlist('end_user_usds')
            end_user_ghcs = request.form.getlist('end_user_ghcs')
            super_dealer_usds = request.form.getlist('super_dealer_usds')
            super_dealer_ghcs = request.form.getlist('super_dealer_ghcs')

            update_query = """
            UPDATE Items_List
            SET Item_Description = %s, Retail_Price_With_Tax = %s, Super_Dealer_Price_With_Tax = %s,
                End_User_USD = %s, End_User_GHC = %s, Super_Dealer_USD = %s, Super_Dealer_GHC = %s
            WHERE Item_ID = %s
            """

            for i in range(len(item_ids)):
                # Skip rows with blank values
                if any(field.strip() == '' for field in [item_descriptions[i], retail_prices_with_tax[i], super_dealer_prices_with_tax[i]]):
                    continue

                try:
                    cursor.execute(update_query, (
                        item_descriptions[i], retail_prices_with_tax[i], super_dealer_prices_with_tax[i],
                        end_user_usds[i], end_user_ghcs[i], super_dealer_usds[i], super_dealer_ghcs[i],
                        item_ids[i]
                    ))
                except mysql.connector.errors.IntegrityError as e:
                    print(f"Duplicate entry error: {e}")
                    message += f"Duplicate entry detected for Item Description: '{item_descriptions[i]}'.<br>"

            connection.commit()

            if message:
                message = 'Some updates failed due to duplicate entries.<br>' + message

        cursor.close()
        connection.close()

    else:
        flash('Database connection failed.')

    if message:
        flash(message)

    return redirect(url_for('item_list'))

@app.route('/delete_item/<item_id>', methods=['POST'])
def delete_item(item_id):
    connection = get_sql_connection()
    if connection:
        cursor = connection.cursor()
        try:
            cursor.execute("DELETE FROM Items_List WHERE Item_ID = %s", (item_id,))
            connection.commit()
            flash('Item deleted successfully.')
        except mysql.connector.Error as err:
            print(f"Database error: {err}")
            flash('Error deleting item.')
        finally:
            cursor.close()
            connection.close()
    else:
        flash('Database connection failed.')

    return redirect(url_for('item_list'))

@app.route('/autocomplete_member', methods=['GET'])
def autocomplete_member():
    search = request.args.get('term', '')

    logging.debug(f"Received term: {search}")  # Log the search term

    try:
        # Use SQLAlchemy to query the database
        suggestions = (
            db.session.query(Team_Members.Team_Member_Name)
            .filter(Team_Members.Team_Member_Name.like(f"%{search}%"))
            .all()
        )

        # Flatten the list of tuples into a list of names
        suggestions = [member[0] for member in suggestions]

    except Exception as e:
        logging.error(f"Error during autocomplete_member query: {e}")
        suggestions = []

    logging.debug(f"Suggestions: {suggestions}")  # Log the suggestions being returned

    return jsonify(suggestions)

"""
@app.route('/autocomplete_member', methods=['GET'])
def autocomplete_member():
    search = request.args.get('term', '')

    logging.debug(f"Received term: {search}")  # Log the search term

    # Establish a new connection
    connection = get_sql_connection()
    cursor = connection.cursor()

    query = """
#        SELECT Team_Member_Name
#        FROM Team_Members
#        WHERE Team_Member_Name LIKE %s
#    """
"""
    try:
        cursor.execute(query, (f"%{search}%",))
        results = cursor.fetchall()
        suggestions = [result[0] for result in results]
    except Exception as e:
        logging.error(f"Error during autocomplete_member query: {e}")
        suggestions = []

    finally:
        cursor.close()
        connection.close()

    logging.debug(f"Suggestions: {suggestions}")  # Log the suggestions being returned

    return jsonify(suggestions)
"""

from sqlalchemy import literal_column

@app.route('/autocomplete_client', methods=['GET'])
def autocomplete_client():
    term = request.args.get('term', '')

    try:
        # Properly format the term for SQL LIKE
        search_term = f"%{term}%"

        # Use SQLAlchemy to query the database
        client_names = (
            db.session.query(Client_List.Client_Name)
            .filter(Client_List.Client_Name.like(search_term))
            .limit(10)
            .all()
        )

        # Flatten the list of tuples into a list of names
        client_name_list = [client[0] for client in client_names]

    except Exception as e:
        logging.error(f"Error during autocomplete_client query: {e}")
        client_name_list = []

    return jsonify(client_name_list)

"""
@app.route('/autocomplete_client', methods=['GET'])
def autocomplete_client():
    term = request.args.get('term')
    connection = get_sql_connection()
    cursor = connection.cursor(dictionary=True)

    # Query for client names matching the search term
    cursor.execute("SELECT Client_Name FROM Client_List WHERE Client_Name LIKE %s LIMIT 10", (f"%{term}%",))
    client_names = cursor.fetchall()

    # Extract the client names and return as a list
    client_name_list = [client['Client_Name'] for client in client_names]
    cursor.close()
    connection.close()

    return jsonify(client_name_list)
"""
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Define the allowed extensions for file uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
#UPLOAD_FOLDER = 'static/uploads'  # Adjust this path according to your setup

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/assign_job', methods=['GET', 'POST'])
def assign_job():
    try:
        if request.method == 'POST':
            client_name = request.form['client_name']
            tasks_performed = request.form['tasks_performed']
            any_issues = request.form['any_issues']
            percentage_completion = request.form['percentage_completion']
            job_date = request.form['job_date']  # Capture the job date from the form
            team_member_ids = request.form.getlist('team_members')

            # Retrieve client information
            client_info = (
                db.session.query(Client_List.Client_Unique_ID, Client_List.Town, Client_List.Phone_Number)
                .filter(Client_List.Client_Name == client_name)
                .first()
            )

            if not client_info:
                logging.error(f"Client not found: {client_name}")
                return "Client not found", 404

            client_unique_id, town, phone_number = client_info

            # Insert into Job_Tracking
            new_job = Job_Tracking(
                Client_Unique_ID=client_unique_id,
                Client_Name=client_name,
                Town=town,
                Phone_Number=phone_number,
                Date=job_date,
                Tasks_Performed=tasks_performed,
                Any_Issues=any_issues,
                Percentage_Completion=percentage_completion
            )
            db.session.add(new_job)
            db.session.commit()

            job_id = new_job.Job_ID
            logging.info(f"Job ID created: {job_id}")

            # Insert into job_team_members and Team_Members_Assigned
            for team_member_id in team_member_ids:
                job_team_member = job_team_members(Job_ID=job_id, Team_Member_ID=team_member_id)
                team_member_assigned = Team_Members_Assigned(Job_ID=job_id, Team_Member_ID=team_member_id)
                db.session.add(job_team_member)
                db.session.add(team_member_assigned)

            logging.info(f"Team members assigned to job ID {job_id}: {team_member_ids}")

            # Handle file uploads
            if 'job_pictures' in request.files:
                files = request.files.getlist('job_pictures')
                if files:
                    for file in files:
                        if file and allowed_file(file.filename):
                            filename = secure_filename(file.filename)
                            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                            file.save(file_path)

                            # Insert file info into the database
                            job_picture = Job_Pictures(Job_ID=job_id, Picture_URL=filename)
                            db.session.add(job_picture)
                            logging.info(f"File uploaded and path inserted into DB: {filename}")
                else:
                    job_picture = Job_Pictures(Job_ID=job_id, Picture_URL=None)
                    db.session.add(job_picture)
                    logging.info(f"No pictures uploaded. Inserted Job_ID {job_id} with NULL Picture_URL")
            else:
                job_picture = Job_Pictures(Job_ID=job_id, Picture_URL=None)
                db.session.add(job_picture)
                logging.info(f"No file input provided. Inserted Job_ID {job_id} with NULL Picture_URL")

            db.session.commit()
            logging.info("Job assignment committed to the database.")
            return redirect(url_for('assign_job'))

        # Fetch team members for GET request
        team_members = db.session.query(Team_Members.Team_Member_ID, Team_Members.Team_Member_Name).all()

        return render_template('assign_job.html', team_members=team_members)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        db.session.rollback()
        return str(e)


"""
@app.route('/assign_job', methods=['GET', 'POST'])
def assign_job():
    try:
        mydb = get_sql_connection()
        cursor = mydb.cursor()

        if request.method == 'POST':
            client_name = request.form['client_name']
            tasks_performed = request.form['tasks_performed']
            any_issues = request.form['any_issues']
            percentage_completion = request.form['percentage_completion']
            job_date = request.form['job_date']  # Capture the job date from the form
            team_member_ids = request.form.getlist('team_members')

            # Retrieve client information
            cursor.execute("""
#                SELECT Client_Unique_ID, Town, Phone_Number
#                FROM Client_List
#                WHERE Client_Name = %s
#            """, (client_name,))
"""            client_info = cursor.fetchone()

            if not client_info:
                logging.error(f"Client not found: {client_name}")
                return "Client not found", 404

            client_unique_id, town, phone_number = client_info

            # Insert into Job_Tracking and retrieve the generated Job_ID
            cursor.execute("""
#                INSERT INTO Job_Tracking (Client_Unique_ID, Client_Name, Town, Phone_Number, Date, Tasks_Performed, Any_Issues, Percentage_Completion)
#                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
#            """, (client_unique_id, client_name, town, phone_number, job_date, tasks_performed, any_issues, percentage_completion))
"""
            # Fetch the auto-generated Job_ID
            job_id = cursor.lastrowid
            logging.info(f"Job ID created: {job_id}")

            # Insert into Job_Team_Members and Team_Members_Assigned
            for team_member_id in team_member_ids:
                cursor.execute("""
#                    INSERT INTO Job_Team_Members (Job_ID, Team_Member_ID)
#                    VALUES (%s, %s)
#                """, (job_id, team_member_id))
"""
                cursor.execute("""
#                    INSERT INTO Team_Members_Assigned (Job_ID, Team_Member_ID)
#                    VALUES (%s, %s)
#                """, (job_id, team_member_id))
"""
            logging.info(f"Team members assigned to job ID {job_id}: {team_member_ids}")

            # Handle file uploads
            if 'job_pictures' in request.files:
                files = request.files.getlist('job_pictures')
                if files:
                    for file in files:
                        if file and allowed_file(file.filename):
                            filename = secure_filename(file.filename)
                            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                            file.save(file_path)

                            # Insert file info into the database
                            cursor.execute("""
#                                INSERT INTO Job_Pictures (Job_ID, Picture_URL)
#                                VALUES (%s, %s)
#                            """, (job_id, filename))
"""
                            logging.info(f"File uploaded and path inserted into DB: {filename}")
                else:
                    cursor.execute("""
"""
#                        INSERT INTO Job_Pictures (Job_ID, Picture_URL)
#                        VALUES (%s, NULL)
#                    """
#, (job_id,))
"""
"""
#                    logging.info(f"No pictures uploaded. Inserted Job_ID {job_id} with NULL Picture_URL")
#            else:
"""
#                cursor.execute("""
#                    INSERT INTO Job_Pictures (Job_ID, Picture_URL)
#                    VALUES (%s, NULL)
#                """, (job_id,))
"""
                logging.info(f"No file input provided. Inserted Job_ID {job_id} with NULL Picture_URL")

            mydb.commit()
            logging.info("Job assignment committed to the database.")
            return redirect(url_for('index'))

        # Fetch team members for GET request
        cursor.execute("SELECT Team_Member_ID, Team_Member_Name FROM Team_Members")
        team_members = cursor.fetchall()

        return render_template('assign_job.html', team_members=team_members)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        if 'mydb' in locals():
            mydb.rollback()
        return str(e)

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'mydb' in locals():
            mydb.close()
"""

@app.route('/checklist', methods=['GET', 'POST'])
def checklist():
    try:
        # Fetch all team members from the database
        team_members = db.session.query(Team_Members).all()

        if request.method == 'POST':
            # Handle form submission
            team_member_id = request.form['team_member']
            crosschecker_id = request.form['crosschecker']

            # Process the selected team members (e.g., save to the database, etc.)
            # You can add your own logic for handling this part

            # Redirect or return a success response after processing
            return redirect('/checklist')  # Redirect back to the checklist page or any other page

        # Render the checklist template, passing the team_members to the template
        return render_template('checklist.html', team_members=team_members)

    except Exception as e:
        # Log the error and return a 500 response
        app.logger.error(f"Exception on /checklist: {e}")
        return "An error occurred", 500


@app.route('/spy', methods=['GET', 'POST'])
def spy():
    try:
        if request.method == 'POST':
            # Retrieve the submitted date
            selected_date = request.form['date']

            # Check if no client and team details are provided
            client_provided = any(key.startswith('client_') for key in request.form)
            team_provided = any(key.startswith('team_') for key in request.form)

            if not client_provided and not team_provided:
                # Query the database for records corresponding to the selected date
                results = Assigned_Teams.query.filter_by(assignment_date=selected_date).all()

                if results:
                    # Prepare the data to populate the form fields
                    data_to_display = []
                    for row in results:
                        data_to_display.append({
                            'client_name': row.client_name,
                            'location': row.location,
                            'phone_number': row.phone_number,
                            'assigned_team': row.assigned_team
                        })

                    return render_template('spy.html',
                                           selected_date=selected_date,
                                           data_to_display=data_to_display)

            else:
                # Client and team details are provided, handle submission
                client_team_pairs = []
                for key, value in request.form.items():
                    if 'client_' in key:
                        client_index = key.split('_')[1]  # Extract index from the key
                        client_name = value
                        team_name = request.form.get(f'team_{client_index}')
                        location = request.form.get(f'location_{client_index}')  # Get location
                        phone_number = request.form.get(f'phone_{client_index}')  # Get phone number
                        client_team_pairs.append((client_name, team_name, location, phone_number))

                # Insert or update the data in the database
                for client_name, team_name, location, phone_number in client_team_pairs:
                    existing_assignment = Assigned_Teams.query.filter_by(client_name=client_name, assignment_date=selected_date).first()

                    if existing_assignment:
                        # Update existing assignment
                        existing_assignment.assigned_team = team_name
                        existing_assignment.location = location
                        existing_assignment.phone_number = phone_number
                    else:
                        # Create a new assignment
                        new_assignment = Assigned_Teams(
                            client_name=client_name,
                            assigned_team=team_name,
                            assignment_date=selected_date,
                            location=location,
                            phone_number=phone_number
                        )
                        db.session.add(new_assignment)

                db.session.commit()  # Commit the changes
                return redirect(url_for('spy'))

        # Fetch clients and team members for the form's autocomplete
        clients = Client_List.query.all()
        team_members = Team_Members.query.all()

        return render_template('spy.html', clients=clients, team_members=team_members)

    except SQLAlchemyError as e:
        logging.error(f"SQLAlchemy error during team assignment: {e}")
        db.session.rollback()
        return str(e)

    finally:
        db.session.close()


@app.route('/assign_teams', methods=['GET', 'POST'])
def assign_teams():
    try:
        if request.method == 'POST':
            # Retrieve the submitted date
            selected_date = request.form['date']

            # Check if no client and team details are provided
            client_provided = any(key.startswith('client_') for key in request.form)
            team_provided = any(key.startswith('team_') for key in request.form)

            if not client_provided and not team_provided:
                # Query the database for records corresponding to the selected date
                results = Assigned_Teams.query.filter_by(assignment_date=selected_date).all()

                if results:
                    # Prepare the data to populate the form fields
                    data_to_display = []
                    for row in results:
                        data_to_display.append({
                            'client_name': row.client_name,
                            'location': row.location,
                            'phone_number': row.phone_number,
                            'assigned_team': row.assigned_team
                        })

                    return render_template('assign_teams.html',
                                           selected_date=selected_date,
                                           data_to_display=data_to_display)

            else:
                # Client and team details are provided, handle submission
                client_team_pairs = []
                for key, value in request.form.items():
                    if 'client_' in key:
                        client_index = key.split('_')[1]  # Extract index from the key
                        client_name = value
                        team_name = request.form.get(f'team_{client_index}')
                        location = request.form.get(f'location_{client_index}')  # Get location
                        phone_number = request.form.get(f'phone_{client_index}')  # Get phone number
                        client_team_pairs.append((client_name, team_name, location, phone_number))

                # Insert or update the data in the database
                for client_name, team_name, location, phone_number in client_team_pairs:
                    existing_assignment = Assigned_Teams.query.filter_by(client_name=client_name, assignment_date=selected_date).first()

                    if existing_assignment:
                        # Update existing assignment
                        existing_assignment.assigned_team = team_name
                        existing_assignment.location = location
                        existing_assignment.phone_number = phone_number
                    else:
                        # Create a new assignment
                        new_assignment = Assigned_Teams(
                            client_name=client_name,
                            assigned_team=team_name,
                            assignment_date=selected_date,
                            location=location,
                            phone_number=phone_number
                        )
                        db.session.add(new_assignment)

                db.session.commit()  # Commit the changes
                return redirect(url_for('assign_teams'))

        # Fetch clients and team members for the form's autocomplete
        clients = Client_List.query.all()
        team_members = Team_Members.query.all()

        return render_template('assign_teams.html', clients=clients, team_members=team_members)

    except SQLAlchemyError as e:
        logging.error(f"SQLAlchemy error during team assignment: {e}")
        db.session.rollback()
        return str(e)

    finally:
        db.session.close()

"""
@app.route('/assign_teams', methods=['GET', 'POST'])
def assign_teams():
    try:
        mydb = get_sql_connection()
        cursor = mydb.cursor()

        if request.method == 'POST':
            # Retrieve the submitted date
            selected_date = request.form['date']

            # Check if no client and team details are provided
            client_provided = any(key.startswith('client_') for key in request.form)
            team_provided = any(key.startswith('team_') for key in request.form)

            if not client_provided and not team_provided:
                # Query the database for records corresponding to the selected date
                query = """
#                    SELECT client_name, location, phone_number, assigned_team
#                    FROM Assigned_Teams
#                    WHERE assignment_date = %s
#                """
"""
                cursor.execute(query, (selected_date,))
                results = cursor.fetchall()

                if results:
                    # Prepare the data to populate the form fields
                    data_to_display = []
                    for row in results:
                        data_to_display.append({
                            'client_name': row[0],
                            'location': row[1],
                            'phone_number': row[2],
                            'assigned_team': row[3]
                        })

                    return render_template('assign_teams.html',
                                           selected_date=selected_date,
                                           data_to_display=data_to_display)

            else:
                # Client and team details are provided, handle submission
                client_team_pairs = []
                for key, value in request.form.items():
                    if 'client_' in key:
                        client_index = key.split('_')[1]  # Extract index from the key
                        client_name = value
                        team_name = request.form.get(f'team_{client_index}')
                        location = request.form.get(f'location_{client_index}')  # Get location
                        phone_number = request.form.get(f'phone_{client_index}')  # Get phone number
                        client_team_pairs.append((client_name, team_name, location, phone_number))

                # Insert or update the data in the database
                for client_name, team_name, location, phone_number in client_team_pairs:
"""
                    # Insert or update client, team, location, and phone number
#                    query = """
#                        INSERT INTO Assigned_Teams (client_name, assigned_team, assignment_date, location, phone_number)
#                        VALUES (%s, %s, %s, %s, %s)
#                        ON DUPLICATE KEY UPDATE
#                            assigned_team = VALUES(assigned_team),
#                            location = VALUES(location),
#                            phone_number = VALUES(phone_number)
#                    """
"""
                    cursor.execute(query, (client_name, team_name, selected_date, location, phone_number))

                mydb.commit()  # Commit the changes

                return render_template('assign_teams.html', team_name=team_name)

        # Fetch clients and team members for the form's autocomplete
        cursor.execute("SELECT Client_Unique_ID, Client_Name, Town FROM Client_List")
        clients = cursor.fetchall()

        cursor.execute("SELECT Team_Member_ID, Team_Member_Name FROM Team_Members")
        team_members = cursor.fetchall()

        return render_template('assign_teams.html', clients=clients, team_members=team_members)

    except Exception as e:
        logging.error(f"Error during team assignment: {e}")
        return str(e)

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'mydb' in locals():
            mydb.close()
"""


@app.route('/get_client_details', methods=['GET'])
def get_client_details():
    client_name = request.args.get('client_name')
    try:
        # Query to get the town and phone number based on the client name
        result = Client_List.query.filter_by(Client_Name=client_name).first()

        if result:
            return jsonify({'town': result.Town, 'phone_number': result.Phone_Number})
        else:
            return jsonify({'town': '', 'phone_number': ''})

    except Exception as e:
        logging.error(f"Error fetching client details: {e}")
        return jsonify({'town': '', 'phone_number': ''})

    finally:
        db.session.close()

"""
@app.route('/get_client_details', methods=['GET'])
def get_client_details():
    client_name = request.args.get('client_name')
    try:
        mydb = get_sql_connection()
        cursor = mydb.cursor()

        # Query to get the town and phone number based on the client name
        cursor.execute("SELECT Town, Phone_Number FROM Client_List WHERE Client_Name = %s", (client_name,))
        result = cursor.fetchone()

        if result:
            town, phone_number = result
            return jsonify({'town': town, 'phone_number': phone_number})
        else:
            return jsonify({'town': '', 'phone_number': ''})

    except Exception as e:
        logging.error(f"Error fetching client details: {e}")
        return jsonify({'town': '', 'phone_number': ''})

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'mydb' in locals():
            mydb.close()
"""

@app.route('/summary', methods=['GET', 'POST'])
def summary():
    try:
        # Initialize variables for form data
        filter_type = ''
        team_member_name = ''
        start_date = ''
        end_date = ''
        group_by = 'Client_Name'  # Default grouping by Client Name

        # Fetch team members for autocomplete/dropdown
        team_members = Team_Members.query.all()

        if request.method == 'POST':
            # Get the form data
            filter_type = request.form.get('filter_type', '')
            team_member_name = request.form.get('team_member', '')
            start_date = request.form.get('start_date', '')
            end_date = request.form.get('end_date', '')
            group_by = request.form.get('group_by', 'Client_Name')  # Default to Client_Name if not provided

            logging.debug(f"Filter Type: {filter_type}")
            logging.debug(f"Team Member Name: {team_member_name}")
            logging.debug(f"Start Date: {start_date}")
            logging.debug(f"End Date: {end_date}")
            logging.debug(f"Group By: {group_by}")

            conditions = []

            # Filtering based on the filter type
            if filter_type == 'team_member' and team_member_name:
                team_member = Team_Members.query.filter_by(Team_Member_Name=team_member_name).first()
                if not team_member:
                    logging.error(f"No team member found with name: {team_member_name}")
                    return render_template(
                        'summary.html',
                        error="No job details to display.",
                        team_members=team_members,
                        filter_type=filter_type,
                        team_member_name=team_member_name,
                        start_date=start_date,
                        end_date=end_date,
                        group_by=group_by
                    )
                conditions.append(job_team_members.Team_Member_ID == team_member.Team_Member_ID)

            if (filter_type == 'date' or filter_type == 'both') and start_date and end_date:
                conditions.append(Job_Tracking.Date.between(start_date, end_date))

            # Handle grouping
            group_column_map = {
                "Client_Name": Client_List.Client_Name,
                "Town": Client_List.Town,
                "Date": Job_Tracking.Date
            }

            # Ensure group_column is a valid column or wrap it in text() for string literals
            if group_by in group_column_map:
                group_column = group_column_map[group_by]
            else:
                group_column = text(group_by)

            # Query to get the job details with filters
            jobs_query = db.session.query(
                Job_Tracking.Job_ID,
                func.max(Client_List.Client_Name).label('Client_Name'),
                func.max(Client_List.Town).label('Town'),
                func.max(Client_List.Phone_Number).label('Phone_Number'),
                Job_Tracking.Date,
                func.max(Job_Tracking.Tasks_Performed).label('Tasks_Performed'),
                func.max(Job_Tracking.Any_Issues).label('Any_Issues'),
                func.max(Job_Tracking.Percentage_Completion).label('Percentage_Completion'),
                func.group_concat(func.distinct(Team_Members.Team_Member_Name)).label('Engineers')
            ).join(Client_List, Job_Tracking.Client_Unique_ID == Client_List.Client_Unique_ID
            ).outerjoin(job_team_members, Job_Tracking.Job_ID == job_team_members.Job_ID
            ).outerjoin(Team_Members, job_team_members.Team_Member_ID == Team_Members.Team_Member_ID
            ).filter(and_(*conditions)
            ).group_by(Job_Tracking.Job_ID, group_column
            ).order_by(Job_Tracking.Date.desc())

            jobs = jobs_query.all()

            # Group jobs by selected group_by option
            grouped_jobs = {}
            for job in jobs:
                group_key = job.Client_Name if group_by == "Client_Name" else job.Town if group_by == "Town" else job.Date
                if group_key not in grouped_jobs:
                    grouped_jobs[group_key] = []
                grouped_jobs[group_key].append(job)

            # Part 1: Add logic for finding clients with Percentage_Completion < 100% in the last 90 days from end_date
            clients_with_incomplete_jobs = []
            if end_date:
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
                ninety_days_ago = end_date_obj - timedelta(days=90)  # Calculate 90 days from the end_date

                incomplete_query = db.session.query(
                    Client_List.Client_Name,
                    func.max(Job_Tracking.Date).label('Last_Job_Date'),
                    func.max(Job_Tracking.Percentage_Completion).label('Percentage_Completion')
                ).join(Job_Tracking, Client_List.Client_Unique_ID == Job_Tracking.Client_Unique_ID
                ).filter(
                    Job_Tracking.Date.between(ninety_days_ago, end_date)  # Only look in the last 90 days up to end_date
                ).group_by(Client_List.Client_Name).having(
                    func.max(Job_Tracking.Percentage_Completion) < 100  # Ensure the last job is incomplete
                )

                clients_with_incomplete_jobs = incomplete_query.all()

            return render_template(
                'summary.html',
                grouped_jobs=grouped_jobs,
                clients_with_incomplete_jobs=clients_with_incomplete_jobs,  # Add to the context
                team_members=team_members,
                filter_type=filter_type,
                team_member_name=team_member_name,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by
            )

        # If GET request, render the form without any filtering applied
        return render_template(
            'summary.html',
            team_members=team_members,
            filter_type=filter_type,
            team_member_name=team_member_name,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error occurred: {e}")
        return str(e)

    finally:
        db.session.close()


"""
@app.route('/summary', methods=['GET', 'POST'])
def summary():
    try:
        mydb = get_sql_connection()
        cursor = mydb.cursor()

        if request.method == 'POST':
            filter_type = request.form['filter_type']
            team_member_name = request.form['team_member']
            start_date = request.form['start_date']
            end_date = request.form['end_date']
            group_by = request.form['group_by']

            logging.debug(f"Filter Type: {filter_type}")
            logging.debug(f"Team Member Name: {team_member_name}")
            logging.debug(f"Start Date: {start_date}")
            logging.debug(f"End Date: {end_date}")
            logging.debug(f"Group By: {group_by}")

            conditions = []
            params = []

            # Filtering based on the filter type
            if filter_type == 'team_member' and team_member_name:
                cursor.execute("SELECT Team_Member_ID FROM Team_Members WHERE Team_Member_Name = %s", (team_member_name,))
                team_member = cursor.fetchone()
                if not team_member:
                    logging.error(f"No team member found with name: {team_member_name}")
                    return render_template('summary.html', error="No job details to display.")
                conditions.append("jtm.Team_Member_ID = %s")
                params.append(team_member[0])

            if (filter_type == 'date' or filter_type == 'both') and start_date and end_date:
                conditions.append("j.Date BETWEEN %s AND %s")
                params.extend([start_date, end_date])

            # Handle grouping
            group_column_map = {
                "Client_Name": "c.Client_Name",
                "Town": "c.Town",
                "Date": "j.Date"
            }

            if group_by in group_column_map:
                group_column = group_column_map[group_by]
            else:
                group_column = "j.Job_ID"  # Default

            where_clause = " AND ".join(conditions) if conditions else "1"

            query = f"""
#                SELECT
#                    j.Job_ID,
#                    MAX(c.Client_Name) AS Client_Name,
#                    MAX(c.Town) AS Town,
##                    j.Date,
#                    MAX(j.Tasks_Performed) AS Tasks_Performed,
#                    MAX(j.Any_Issues) AS Any_Issues,
#                    MAX(j.Percentage_Completion) AS Percentage_Completion,
#                    GROUP_CONCAT(DISTINCT tm.Team_Member_Name) as Engineers,
#                    GROUP_CONCAT(DISTINCT jp.Picture_URL) as Pictures
#                    Job_Tracking j
#                JOIN
#                    Client_List c ON j.Client_Unique_ID = c.Client_Unique_ID
#                LEFT JOIN
#                    Job_Team_Members jtm ON j.Job_ID = jtm.Job_ID
#                LEFT JOIN
#                    Team_Members tm ON jtm.Team_Member_ID = tm.Team_Member_ID
#                LEFT JOIN
##                WHERE {where_clause}
#                GROUP BY j.Job_ID, {group_column}
#                ORDER BY j.Date DESC
#            """
"""

            logging.debug(f"Final Query: {query}")
            cursor.execute(query, params)
            jobs = cursor.fetchall()

            # Fetch team members for the dropdown
            cursor.execute("SELECT Team_Member_ID, Team_Member_Name FROM Team_Members")
            team_members = cursor.fetchall()

            # Group jobs by selected group_by option
            grouped_jobs = {}
            for job in jobs:
                group_key = job[1] if group_by == "Client_Name" else job[2] if group_by == "Town" else job[4]
                if group_key not in grouped_jobs:
                    grouped_jobs[group_key] = []
                grouped_jobs[group_key].append(job)

            return render_template('summary.html', grouped_jobs=grouped_jobs, team_members=team_members)

        # Fetch team members for the dropdown
        cursor.execute("SELECT Team_Member_ID, Team_Member_Name FROM Team_Members")
        team_members = cursor.fetchall()

        return render_template('summary.html', team_members=team_members)

    except Exception as e:
        if 'mydb' in locals():
            mydb.rollback()
        logging.error(f"Error occurred: {e}")
        return str(e)

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'mydb' in locals():
            mydb.close()

"""

@app.route('/client_summary', methods=['GET', 'POST'])
def client_summary():
    try:
        jobs = []
        grouped_jobs = None  # Initialize 'grouped_jobs' as None

        if request.method == 'POST':
            filter_type = request.form.get('filter_type')
            client_name = request.form.get('client_name')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            group_by = request.form.get('group_by')

            # Base query
            query = db.session.query(
                Job_Tracking.Job_ID,
                Client_List.Client_Name,
                Client_List.Town,
                Client_List.Phone_Number,
                Job_Tracking.Date,
                Job_Tracking.Tasks_Performed,
                Job_Tracking.Any_Issues,
                Job_Tracking.Percentage_Completion,
                func.group_concat(func.distinct(Team_Members.Team_Member_Name)).label('Engineers'),
                func.group_concat(func.distinct(Job_Pictures.Picture_URL)).label('Pictures')
            ).join(Client_List, Job_Tracking.Client_Unique_ID == Client_List.Client_Unique_ID
            ).outerjoin(Team_Members_Assigned, Job_Tracking.Job_ID == Team_Members_Assigned.Job_ID
            ).outerjoin(Team_Members, Team_Members_Assigned.Team_Member_ID == Team_Members.Team_Member_ID
            ).outerjoin(Job_Pictures, Job_Tracking.Job_ID == Job_Pictures.Job_ID
            ).filter(True)  # Placeholder for dynamic filtering conditions

            # Apply filters based on user input
            if client_name:
                query = query.filter(Client_List.Client_Name == client_name)
            if start_date and end_date:
                query = query.filter(Job_Tracking.Date.between(start_date, end_date))

            # Group by and order
            query = query.group_by(Job_Tracking.Job_ID, Client_List.Client_Name).order_by(Job_Tracking.Date.desc())

            jobs = query.all()

            # Grouping logic based on selected group_by option
            group_by_mapping = {
                'Client_Name': lambda job: job.Client_Name,
                'Town': lambda job: job.Town,
                'Date': lambda job: job.Date,
                'Engineers': lambda job: job.Engineers
            }

            if group_by:
                grouped_jobs = {}
                group_key_fn = group_by_mapping.get(group_by)
                if group_key_fn:
                    for job in jobs:
                        group_key = group_key_fn(job)
                        if group_key not in grouped_jobs:
                            grouped_jobs[group_key] = []
                        grouped_jobs[group_key].append(job)

        return render_template('client_summary.html', grouped_jobs=grouped_jobs, jobs=jobs if not grouped_jobs else None)

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error occurred: {e}")
        return str(e)

    finally:
        db.session.close()


"""
@app.route('/client_summary', methods=['GET', 'POST'])
def client_summary():
    try:
        mydb = get_sql_connection()
        cursor = mydb.cursor()

        jobs = []
        grouped_jobs = None  # Initialize 'grouped_jobs' as None

        if request.method == 'POST':
            filter_type = request.form['filter_type']
            client_name = request.form.get('client_name')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            group_by = request.form.get('group_by')

            # Base query
            query = """
#                SELECT jt.Job_ID, cl.Client_Name, cl.Town, cl.Phone_Number, jt.Date, jt.Tasks_Performed, jt.Any_Issues, jt.Percentage_Completion,
#                       GROUP_CONCAT(DISTINCT tm.Team_Member_Name SEPARATOR ', ') AS Engineers,
#                       GROUP_CONCAT(DISTINCT jp.Picture_URL SEPARATOR ', ') AS Pictures
#                FROM Job_Tracking jt
#                JOIN Client_List cl ON jt.Client_Unique_ID = cl.Client_Unique_ID
#                LEFT JOIN Team_Members_Assigned tma ON jt.Job_ID = tma.Job_ID
#                LEFT JOIN Team_Members tm ON tma.Team_Member_ID = tm.Team_Member_ID
#                LEFT JOIN Job_Pictures jp ON jt.Job_ID = jp.Job_ID
#                WHERE 1=1
#            """
"""
            # Append filters based on user input
            params = []
            if client_name:
                query += " AND cl.Client_Name = %s"
                params.append(client_name)
            if start_date and end_date:
                query += " AND jt.Date BETWEEN %s AND %s"
                params.extend([start_date, end_date])

            query += """
#                GROUP BY jt.Job_ID, Client_Name
#                ORDER BY jt.Date DESC;
#            """
"""
            cursor.execute(query, params)
            jobs = cursor.fetchall()

            # Grouping logic based on selected group_by option
            group_by_mapping = {
                'Client_Name': 1,  # Client Name
                'Town': 2,         # Town
                'Date': 4,         # Date
                'Engineers': 8      # Engineers
            }

            if group_by:
                grouped_jobs = {}
                for job in jobs:
                    group_key = job[group_by_mapping[group_by]]  # Group by selected option
                    if group_key not in grouped_jobs:
                        grouped_jobs[group_key] = []
                    grouped_jobs[group_key].append(job)

        return render_template('client_summary.html', grouped_jobs=grouped_jobs, jobs=jobs if not grouped_jobs else None)

    except Exception as e:
        return str(e)

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'mydb' in locals():
            mydb.close()
"""
# Assuming UPLOAD_FOLDER is defined elsewhere in your app.py
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # Log the file path for debugging
    app.logger.info(f"Requested file: {file_path}")

    if not os.path.exists(file_path):
        app.logger.error(f"File not found: {file_path}")
        return jsonify({"error": "File not found"}), 404


    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':

    # Ensure the upload folder exists
    #if not os.path.exists(UPLOAD_FOLDER):
    #    os.makedirs(UPLOAD_FOLDER)

    # Use the port from environment variables; default to 5000 for local development
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)


#    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))  # Use environment variable for port
