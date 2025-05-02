from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_from_directory, abort, send_file
import os
import logging
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import pymysql
from models import db, Client_List, Items_List, Team_Members, Assigned_Teams, job_team_members, Job_Pictures, Team_Members_Assigned, Job_Tracking, client_items, sales_by_item, projects  # Import db only once from models
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
#from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Float, and_, func, literal_column, desc, select, distinct, create_engine, case, text, or_
from sqlalchemy.orm import sessionmaker, aliased
import pandas as pd
from sqlalchemy.sql import text
from datetime import datetime, timedelta, date
import openpyxl
from openpyxl import load_workbook
from fpdf import FPDF
import tempfile
from xhtml2pdf import pisa
import io
from sqlalchemy.sql.expression import true
import decimal
from urllib.parse import urlparse
from flask_mail import Mail, Message
from drive_uploader import upload_to_drive, GOOGLE_DRIVE_FOLDER_ID
from decimal import Decimal


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
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'pdf'}

# Database configuration from environment variables
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{os.getenv('JAWSDB_USER')}:{os.getenv('JAWSDB_PASSWORD')}@{os.getenv('JAWSDB_HOST')}/{os.getenv('JAWSDB_DB')}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable track modifications for performance

# Initialize the database and migration tools
# db = SQLAlchemy(app)  # This line has been removed to prevent multiple initializations
migrate = Migrate(app, db)



# Email configuration
app.config['MAIL_SERVER'] = 'smtp.hostedemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')  # Store in Heroku environment variables
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS')  # Store in Heroku environment variables
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('EMAIL_USER')

mail = Mail(app)



# Initialize the SQLAlchemy object with the app context
db.init_app(app)

# Check if environment variables are set
if not all([os.getenv('JAWSDB_HOST'), os.getenv('JAWSDB_USER'), os.getenv('JAWSDB_PASSWORD'), os.getenv('JAWSDB_DB')]):
    logging.error("One or more JAWSDB environment variables are not set")
    raise EnvironmentError("Database environment variables are not set")

@app.route('/test_schema')
def test_schema():
    connection = get_sql_connection()
    if connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DATABASE()")
                schema_name = cursor.fetchone()
                return f"Connected to schema: {schema_name['DATABASE()']}"
        except Exception as e:
            logging.error(f"Error fetching schema: {e}")
            return "Error fetching schema"
    return "Connection failed"


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
        # Get the JAWSDB_URL from Heroku config
        database_url = os.getenv('JAWSDB_URL')

        if not database_url:
            logging.error("Database URL not found in environment variables")
            return None

        # Parse the database URL using urlparse
        parsed_url = urlparse(database_url)

        # Extract connection details from the parsed URL
        connection = pymysql.connect(
            host=parsed_url.hostname,
            user=parsed_url.username,
            password=parsed_url.password,
            database=parsed_url.path[1:],  # Remove the leading slash
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




# Configuration for the folder containing the Excel files
EXCEL_FOLDER = os.path.join(os.getcwd(), 'static', 'excel')
app.config['EXCEL_FOLDER'] = EXCEL_FOLDER

@app.route('/invoice_generation', methods=['GET'])
def invoice_generation():
    """Render the invoice generation page."""
    return render_template('invoice_generation.html')


@app.route('/download_excel', methods=['GET'])
def download_excel():
    """Provide the sample Excel file for download with a dynamic filename."""
    try:
        filepath = os.path.join(app.config['EXCEL_FOLDER'], 'sample.xlsx')
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404

        # Generate the filename with the current date
        current_date = datetime.now().strftime('%Y%m%d')
        dynamic_filename = f"{current_date} - Invoice - TSL.xlsx"

        return send_file(filepath, as_attachment=True, download_name=dynamic_filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#from sqlalchemy.sql import text

from collections import defaultdict

@app.route('/graphical_reports', methods=['GET', 'POST'])
def graphical_reports():
    start_date = None
    end_date = None
    team_rankings = []
    client_days_data = []
    inverter_data = []
    inverter_quantity_data = []
    battery_data = []
    battery_quantity_data = []
    solar_panel_data = []
    solar_panel_quantity_data = []
    victron_charge_controller_quantity_data = []  # Default value to avoid UnboundLocalError
    inverter_chart_data = {'labels': [], 'data': []}  # Preprocessed data for the chart
    inverter_quantity_chart_data = {'labels': [], 'data': []}  # Preprocessed data for the inverter quantity chart
    battery_chart_data = {'labels': [], 'data': []}
    battery_quantity_chart_data = {'labels': [], 'data': []}  # Preprocessed data for the battery quantity chart
    solar_panel_chart_data = {'labels': [], 'data': []}
    solar_panel_quantity_chart_data = {'labels': [], 'data': []}  # Preprocessed data for the solar panel quantity chart
    victron_charge_controller_chart_data = {'labels': [], 'data': []}
    victron_charge_controller_quantity_chart_data = {'labels': [], 'data': []}  # Preprocessed data for the victron charge controller quantity chart


    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        if start_date and end_date:
            team_rankings = db.session.execute(
                text("""
                SELECT tm.Team_Member_Name,
                       COUNT(DISTINCT jt.Date) AS days_worked,
                       COUNT(DISTINCT jt.Client_Unique_ID) AS clients_visited,
                       SUM(jt.Percentage_Completion / 100) AS total_days_at_clients,
                       (
                           COUNT(DISTINCT jt.Date) +
                           COUNT(DISTINCT jt.Client_Unique_ID) /
                           COALESCE(SUM(jt.Percentage_Completion / 100), 1)
                       ) AS ranking_score
                FROM Team_Members tm
                LEFT JOIN job_team_members jtm ON tm.Team_Member_ID = jtm.Team_Member_ID
                LEFT JOIN Job_Tracking jt ON jtm.Job_ID = jt.Job_ID
                WHERE jt.Date BETWEEN :start_date AND :end_date
                GROUP BY tm.Team_Member_Name
                ORDER BY ranking_score DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()

            client_days_data = db.session.execute(
                text("""
                SELECT jt.Client_Name,
                       COUNT(DISTINCT jt.Date) AS unique_days_at_client
                FROM Job_Tracking jt
                WHERE jt.Date BETWEEN :start_date AND :end_date
                GROUP BY jt.Client_Name
                ORDER BY unique_days_at_client DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()

            inverter_data = db.session.execute(
                text("""
                SELECT cl.Client_Name,
                       ci.Item_Description,
                       ROUND(SUM(ci.quantity * il.kVA_kW), 2) AS total_inverter_capacity,
                       SUM(ci.quantity) AS total_inverter_quantity,
                       ci.installed_by
                FROM client_items ci
                JOIN Items_List il
                  ON ci.item_description = il.Item_Description OR ci.item_description = il.Alias_Description
                JOIN Client_List cl
                  ON ci.client_name = cl.Client_Name OR ci.client_name = cl.Alias_Name
                WHERE ci.component = 'Inverter' AND ci.date BETWEEN :start_date AND :end_date
                GROUP BY cl.Client_Name, ci.installed_by
                ORDER BY total_inverter_capacity DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()

            # Convert result to dictionaries for easier handling
            inverter_data = [
                {
                    'Client_Name': row[0],
                    'Item_Description': row[1],
                    'total_inverter_capacity': row[2],
                    'total_inverter_quantity': row[3],
                    'installed_by': row[4]
                }
                for row in inverter_data
            ]

            # Aggregating inverter capacity
            aggregated_inverter_data = {'Tino Team': 0, 'Client': 0}

            for row in inverter_data:
                if row['installed_by'] in aggregated_inverter_data:
                    aggregated_inverter_data[row['installed_by']] += row['total_inverter_capacity']

            # Preparing inverter data for chart.js
            inverter_chart_data = {
                'labels': list(aggregated_inverter_data.keys()),
                'data': [float(value) for value in aggregated_inverter_data.values()]  # Convert Decimal to float
            }


            inverter_quantity_data = db.session.execute(
                text("""
                SELECT ci.Item_Description,
                       SUM(ci.quantity) AS total_inverter_quantity,
                       ci.installed_by
                FROM client_items ci
                JOIN Items_List il
                  ON ci.item_description = il.Item_Description OR ci.item_description = il.Alias_Description
                WHERE ci.component = 'Inverter' AND ci.date BETWEEN :start_date AND :end_date
                GROUP BY ci.Item_Description, ci.installed_by  -- Group by Item_Description and installed_by
                ORDER BY total_inverter_quantity DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()


            # Convert result to dictionaries for easier handling
            inverter_quantity_data = [
                {
                    'Item_Description': row[0],
                    'total_inverter_quantity': row[1],
                    'installed_by': row[2]
                }
                for row in inverter_quantity_data
            ]

            # Aggregating inverter quantities for each Item_Description
            aggregated_inverter_quantity = defaultdict(lambda: {'Tino Team': 0, 'Client': 0})

            for row in inverter_quantity_data:
                description = row['Item_Description']
                quantity = row['total_inverter_quantity']
                installed_by = row['installed_by']

                # Add the quantity to the corresponding installed_by category
                if installed_by in aggregated_inverter_quantity[description]:
                    aggregated_inverter_quantity[description][installed_by] += quantity

            # Sorting aggregated inverter quantities by value in descending order
            sorted_inverter_quantity = sorted(
                [(description, sum(data.values())) for description, data in aggregated_inverter_quantity.items()],
                key=lambda x: x[1],  # Sort by quantity (value)
                reverse=True         # Descending order
            )

            # Preparing inverter data for chart.js
            inverter_quantity_chart_data = {
                'labels': [item[0] for item in sorted_inverter_quantity],  # Sorted descriptions
                'data': [float(item[1]) for item in sorted_inverter_quantity]  # Sorted quantities
            }

            logging.debug(f"Sorted Inverter Quantities: {inverter_quantity_chart_data}")

            logging.debug(f"Inverter Quantities: {inverter_quantity_chart_data}")
            logging.debug(f"Inverter Chart Data: {inverter_chart_data}")
            logging.debug(f"Inverter Quantity Chart Data: {inverter_quantity_chart_data}")


            print(inverter_quantity_chart_data)  # Check the data


            battery_data = db.session.execute(
                text("""
                SELECT cl.Client_Name,
                       ci.Item_Description,
                       ROUND(SUM(ci.quantity * il.kWh), 2) AS total_battery_capacity,
                       SUM(ci.quantity) AS total_battery_quantity,
                       ci.installed_by
                FROM client_items ci
                JOIN Items_List il
                  ON ci.item_description = il.Item_Description OR ci.item_description = il.Alias_Description
                JOIN Client_List cl
                  ON ci.client_name = cl.Client_Name OR ci.client_name = cl.Alias_Name
                WHERE ci.component = 'Batteries' AND ci.date BETWEEN :start_date AND :end_date
                GROUP BY cl.Client_Name, ci.installed_by
                ORDER BY total_battery_capacity DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()

            # Convert result to dictionaries for easier handling
            battery_data = [
                {
                    'Client_Name': row[0],
                    'Item_Description': row[1],
                    'total_battery_capacity': row[2],
                    'total_battery_quantity': row[3],
                    'installed_by': row[4]
                }
                for row in battery_data
            ]

            # Aggregating battery capacity
            aggregated_battery_data = {'Tino Team': 0, 'Client': 0}

            for row in battery_data:
                if row['installed_by'] in aggregated_battery_data:
                    aggregated_battery_data[row['installed_by']] += row['total_battery_capacity']

            # Preparing battery data for chart.js
            battery_chart_data = {
                'labels': list(aggregated_battery_data.keys()),
                'data': [float(value) for value in aggregated_battery_data.values()]  # Convert Decimal to float
            }


            battery_quantity_data = db.session.execute(
                text("""
                SELECT ci.Item_Description,
                       SUM(ci.quantity) AS total_battery_quantity,
                       ci.installed_by
                FROM client_items ci
                JOIN Items_List il
                  ON ci.item_description = il.Item_Description OR ci.item_description = il.Alias_Description
                WHERE ci.component = 'Batteries' AND ci.date BETWEEN :start_date AND :end_date
                GROUP BY ci.Item_Description, ci.installed_by  -- Group by Item_Description and installed_by
                ORDER BY total_battery_quantity DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()


            # Convert result to dictionaries for easier handling
            battery_quantity_data = [
                {
                    'Item_Description': row[0],
                    'total_battery_quantity': row[1],
                    'installed_by': row[2]
                }
                for row in battery_quantity_data
            ]

            # Aggregating battery quantities for each Item_Description
            aggregated_battery_quantity = defaultdict(lambda: {'Tino Team': 0, 'Client': 0})

            for row in battery_quantity_data:
                description = row['Item_Description']
                quantity = row['total_battery_quantity']
                installed_by = row['installed_by']

                # Add the quantity to the corresponding installed_by category
                if installed_by in aggregated_battery_quantity[description]:
                    aggregated_battery_quantity[description][installed_by] += quantity

            # Sorting aggregated battery quantities by value in descending order
            sorted_battery_quantity = sorted(
                [(description, sum(data.values())) for description, data in aggregated_battery_quantity.items()],
                key=lambda x: x[1],  # Sort by quantity (value)
                reverse=True         # Descending order
            )

            # Preparing battery data for chart.js
            battery_quantity_chart_data = {
                'labels': [item[0] for item in sorted_battery_quantity],  # Sorted descriptions
                'data': [float(item[1]) for item in sorted_battery_quantity]  # Sorted quantities
            }

            logging.debug(f"Sorted Battery Quantities: {battery_quantity_chart_data}")

            logging.debug(f"Battery Quantities: {battery_quantity_chart_data}")
            logging.debug(f"Battery Chart Data: {battery_chart_data}")
            logging.debug(f"Battery Quantity Chart Data: {battery_quantity_chart_data}")


            print(battery_quantity_chart_data)  # Check the data



            # Solar panel data
            solar_panel_data = db.session.execute(
                text("""
                SELECT cl.Client_Name,
                       ROUND(SUM(ci.quantity * il.kVA_kW), 3) AS total_solar_panel_capacity,
                       ci.installed_by
                FROM client_items ci
                JOIN Items_List il ON ci.item_description = il.Item_Description OR ci.item_description = il.Alias_Description
                JOIN Client_List cl ON ci.client_name = cl.Client_Name OR ci.client_name = cl.Alias_Name
                WHERE ci.component = 'Solar Panels' AND ci.date BETWEEN :start_date AND :end_date
                GROUP BY cl.Client_Name, ci.installed_by
                ORDER BY total_solar_panel_capacity DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()

            # Convert result to dictionaries for easier handling
            solar_panel_data = [
                {'Client_Name': row[0], 'total_solar_panel_capacity': row[1], 'installed_by': row[2]}
                for row in solar_panel_data
            ]

            # Aggregating solar panel data
            aggregated_solar_panel_data = {'Tino Team': 0, 'Client': 0}
            for row in solar_panel_data:
                if row['installed_by'] in aggregated_solar_panel_data:
                    aggregated_solar_panel_data[row['installed_by']] += row['total_solar_panel_capacity']

            # Preparing solar panel data for chart.js
            solar_panel_chart_data = {
                'labels': list(aggregated_solar_panel_data.keys()),
                'data': list(aggregated_solar_panel_data.values())
            }


            solar_panel_quantity_data = db.session.execute(
                text("""
                SELECT ci.Item_Description,
                       SUM(ci.quantity) AS total_solar_panel_quantity,
                       ci.installed_by
                FROM client_items ci
                JOIN Items_List il
                  ON ci.item_description = il.Item_Description OR ci.item_description = il.Alias_Description
                WHERE ci.component = 'Solar Panels' AND ci.date BETWEEN :start_date AND :end_date
                GROUP BY ci.Item_Description, ci.installed_by  -- Group by Item_Description and installed_by
                ORDER BY total_solar_panel_quantity DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()


            # Convert result to dictionaries for easier handling
            solar_panel_quantity_data = [
                {
                    'Item_Description': row[0],
                    'total_solar_panel_quantity': row[1],
                    'installed_by': row[2]
                }
                for row in solar_panel_quantity_data
            ]

            # Aggregating solar panel quantities for each Item_Description
            aggregated_solar_panel_quantity = defaultdict(lambda: {'Tino Team': 0, 'Client': 0})

            for row in solar_panel_quantity_data:
                description = row['Item_Description']
                quantity = row['total_solar_panel_quantity']
                installed_by = row['installed_by']

                # Add the quantity to the corresponding installed_by category
                if installed_by in aggregated_solar_panel_quantity[description]:
                    aggregated_solar_panel_quantity[description][installed_by] += quantity

            # Sorting aggregated battery quantities by value in descending order
            sorted_solar_panel_quantity = sorted(
                [(description, sum(data.values())) for description, data in aggregated_solar_panel_quantity.items()],
                key=lambda x: x[1],  # Sort by quantity (value)
                reverse=True         # Descending order
            )

            # Preparing solar panel data for chart.js
            solar_panel_quantity_chart_data = {
                'labels': [item[0] for item in sorted_solar_panel_quantity],  # Sorted descriptions
                'data': [float(item[1]) for item in sorted_solar_panel_quantity]  # Sorted quantities
            }

            logging.debug(f"Sorted Solar Panel Quantities: {solar_panel_quantity_chart_data}")

            logging.debug(f"Solar Panel Quantities: {solar_panel_quantity_chart_data}")
            logging.debug(f"Solar Panel Chart Data: {solar_panel_chart_data}")
            logging.debug(f"Solar Panel Quantity Chart Data: {solar_panel_quantity_chart_data}")


            print(solar_panel_quantity_chart_data)  # Check the data




            victron_charge_controller_quantity_data = db.session.execute(
                text("""
                SELECT ci.Item_Description,
                       SUM(ci.quantity) AS total_victron_charge_controller_quantity,
                       ci.installed_by
                FROM client_items ci
                JOIN Items_List il
                  ON ci.item_description = il.Item_Description OR ci.item_description = il.Alias_Description
                WHERE ci.component = 'Victron Charge Controllers' AND ci.date BETWEEN :start_date AND :end_date
                GROUP BY ci.Item_Description, ci.installed_by  -- Group by Item_Description and installed_by
                ORDER BY total_victron_charge_controller_quantity DESC
                """),
                {'start_date': start_date, 'end_date': end_date}
            ).fetchall()


            # Convert result to dictionaries for easier handling
            victron_charge_controller_quantity_data = [
                {
                    'Item_Description': row[0],
                    'total_victron_charge_controller_quantity': row[1],
                    'installed_by': row[2]
                }
                for row in victron_charge_controller_quantity_data
            ]

            # Aggregating solar panel quantities for each Item_Description
            aggregated_victron_charge_controller_quantity = defaultdict(lambda: {'Tino Team': 0, 'Client': 0})

            for row in victron_charge_controller_quantity_data:
                description = row['Item_Description']
                quantity = row['total_victron_charge_controller_quantity']
                installed_by = row['installed_by']

                # Add the quantity to the corresponding installed_by category
                if installed_by in aggregated_victron_charge_controller_quantity[description]:
                    aggregated_victron_charge_controller_quantity[description][installed_by] += quantity

            # Sorting aggregated battery quantities by value in descending order
            sorted_victron_charge_controller_quantity = sorted(
                [(description, sum(data.values())) for description, data in aggregated_victron_charge_controller_quantity.items()],
                key=lambda x: x[1],  # Sort by quantity (value)
                reverse=True         # Descending order
            )

            # Preparing victron charge controller data for chart.js
            victron_charge_controller_quantity_chart_data = {
                'labels': [item[0] for item in sorted_victron_charge_controller_quantity],  # Sorted descriptions
                'data': [float(item[1]) for item in sorted_victron_charge_controller_quantity]  # Sorted quantities
            }

            logging.debug(f"Sorted Victron Charge Controller Quantities: {victron_charge_controller_quantity_chart_data}")

            logging.debug(f"Victron Charge Controller Quantities: {victron_charge_controller_quantity_chart_data}")
            logging.debug(f"Victron Charge Controller Chart Data: {victron_charge_controller_chart_data}")
            logging.debug(f"Victron Charge Controller Quantity Chart Data: {victron_charge_controller_quantity_chart_data}")


            print(victron_charge_controller_quantity_chart_data)  # Check the data


    return render_template(
        'graphical_reports.html',
        start_date=start_date,
        end_date=end_date,
        team_rankings=team_rankings,
        client_days_data=client_days_data,
        inverter_data=inverter_data,  # Raw data
        inverter_quantity_data=inverter_quantity_data,
        inverter_chart_data=inverter_chart_data,  # Preprocessed inverter data for chart
        inverter_quantity_chart_data=inverter_quantity_chart_data,  # New chart for inverter quantities
        battery_data=battery_data,  # Raw battery data
        battery_quantity_data=battery_quantity_data,
        battery_chart_data=battery_chart_data,  # Preprocessed battery data for chart
        battery_quantity_chart_data=battery_quantity_chart_data,
        solar_panel_data=solar_panel_data,  # Raw solar panel data
        solar_panel_quantity_data=solar_panel_quantity_data,
        solar_panel_chart_data=solar_panel_chart_data,  # Preprocessed solar panel data for chart
        solar_panel_quantity_chart_data=solar_panel_quantity_chart_data,
#        victron_charge_controller_data=victron_charge_controller_data,  # Raw solar panel data
        victron_charge_controller_quantity_data=victron_charge_controller_quantity_data,
        victron_charge_controller_chart_data=victron_charge_controller_chart_data,  # Preprocessed solar panel data for chart
        victron_charge_controller_quantity_chart_data=victron_charge_controller_quantity_chart_data

    )


@app.route('/team_ranking', methods=['GET', 'POST'])
def team_ranking():
    try:
        start_date = None
        end_date = None
        team_rankings = []
        client_days_data = []
        client_employee_days_data = []
        inverter_data = []
        battery_data = []
        solar_panel_data = []
        inverter_quantities = []
        battery_quantities = []
        solar_panel_quantities = []
        victron_charge_controller_quantities = []

        if request.method == 'POST':
            # Check if the request is JSON (AJAX request)
            if request.is_json:
                data = request.get_json()
                start_date = data.get('start_date')
                end_date = data.get('end_date')
            else:
                # Handle traditional form submission
                start_date = request.form['start_date']
                end_date = request.form['end_date']

            # CTE for unique days each client was visited
            client_unique_days_query = db.session.query(
                Job_Tracking.Client_Name,
                func.count(func.distinct(Job_Tracking.Date)).label('unique_days_at_client')
            ).filter(
                Job_Tracking.Date.between(start_date, end_date)
            ).group_by(
                Job_Tracking.Client_Name
            ).cte("client_unique_days")

            # Fetch client days data, sorted by highest unique days first
            client_days_data_query = db.session.query(
                client_unique_days_query.columns.Client_Name,
                client_unique_days_query.columns.unique_days_at_client
            ).filter(client_unique_days_query.columns.Client_Name != None).order_by(client_unique_days_query.columns.unique_days_at_client.desc())

            client_days_data = client_days_data_query.all()

            # Ensure that Client_Name is not None
            client_days_data = [
                {"Client_Name": row.Client_Name, "unique_days_at_client": row.unique_days_at_client}
                for row in client_days_data
                if row.Client_Name is not None
            ]


            # CTE for counting employee-days (distinct employees visiting each client)
            employee_days_query = db.session.query(
                Job_Tracking.Client_Name,
                func.count(job_team_members.Team_Member_ID).label('total_employee_days')
            ).join(
                job_team_members, job_team_members.Job_ID == Job_Tracking.Job_ID
            ).filter(
                Job_Tracking.Date.between(start_date, end_date)
            ).group_by(
                Job_Tracking.Client_Name
            ).cte("employee_days")

            # Fetch client employee-days data
            client_employee_days_data_query = db.session.query(
                employee_days_query.columns.Client_Name,
                employee_days_query.columns.total_employee_days
            ).filter(employee_days_query.columns.Client_Name != None).order_by(employee_days_query.columns.total_employee_days.desc())

            client_employee_days_data = client_employee_days_data_query.all()


            # Query for Inverter data with 'Installed By'
            inverter_data = [
                {
                    "Client_Name": row.Client_Name,
                    "total_inverter_capacity": round(row.total_inverter_capacity or 0, 2),
                    "installed_by": row.installed_by
                }
                for row in db.session.query(
                    func.max(text("Client_List.Client_Name")).label('Client_Name'),
                    func.sum(client_items.quantity * Items_List.kVA_kW).label('total_inverter_capacity'),
                    func.max(client_items.installed_by).label('installed_by')
                ).join(
                    Items_List, or_(
                        client_items.item_description == Items_List.Item_Description,
                        client_items.item_description == Items_List.Alias_Description
                    )
                ).join(
                    Client_List, or_(
                        client_items.client_name == Client_List.Client_Name,
                        client_items.client_name == Client_List.Alias_Name
                    )
                ).filter(
                    client_items.component == 'Inverter',
                    client_items.date.between(start_date, end_date)
                ).group_by(Client_List.Client_Name).order_by(desc('total_inverter_capacity')).all()
            ]

            # Query for Battery data with 'Installed By'
            battery_data = [
                {
                    "Client_Name": row.Client_Name,
                    "total_battery_capacity": round(row.total_battery_capacity or 0, 2),
                    "installed_by": row.installed_by
                }
                for row in db.session.query(
                    func.max(text("Client_List.Client_Name")).label('Client_Name'),
                    func.sum(client_items.quantity * Items_List.kWh).label('total_battery_capacity'),
                    func.max(client_items.installed_by).label('installed_by')
                ).join(
                    Items_List, or_(
                        client_items.item_description == Items_List.Item_Description,
                        client_items.item_description == Items_List.Alias_Description
                    )
                ).join(
                    Client_List, or_(
                        client_items.client_name == Client_List.Client_Name,
                        client_items.client_name == Client_List.Alias_Name
                    )
                ).filter(
                    client_items.component == 'Batteries',
                    client_items.date.between(start_date, end_date)
                ).group_by(Client_List.Client_Name).order_by(desc('total_battery_capacity')).all()
            ]

            # Query for Solar Panel data with 'Installed By'
            solar_panel_data = [
                {
                    "Client_Name": row.Client_Name,
                    "total_solar_panel_capacity": round(row.total_solar_panel_capacity or 0, 3),
                    "installed_by": row.installed_by
                }
                for row in db.session.query(
                    func.max(text("Client_List.Client_Name")).label('Client_Name'),
                    func.sum(client_items.quantity * Items_List.kVA_kW).label('total_solar_panel_capacity'),
                    func.max(client_items.installed_by).label('installed_by')
                ).join(
                    Items_List, or_(
                        client_items.item_description == Items_List.Item_Description,
                        client_items.item_description == Items_List.Alias_Description
                    )
                ).join(
                    Client_List, or_(
                        client_items.client_name == Client_List.Client_Name,
                        client_items.client_name == Client_List.Alias_Name
                    )
                ).filter(
                    client_items.component == 'Solar Panels',
                    client_items.date.between(start_date, end_date)
                ).group_by(Client_List.Client_Name).order_by(desc('total_solar_panel_capacity')).all()
            ]




            # Query for Inverter Quantities
            inverter_quantities = [
                {
                    "Item_Description": row.Item_Description,
                    "total_quantity": row.total_quantity
                }
                for row in db.session.query(
                    Items_List.Item_Description.label('Item_Description'),
                    func.sum(client_items.quantity).label('total_quantity')  # Sum quantities directly from client_items
                ).join(
                    client_items, or_(
                        client_items.item_description == Items_List.Item_Description,
                        client_items.item_description == Items_List.Alias_Description
                    )
                ).filter(
                    Items_List.Component == 'Inverter',  # Ensure filtering by component
                    client_items.date.between(start_date, end_date)
                ).group_by(Items_List.Item_Description)  # Group by Item_Description
                .order_by(desc('total_quantity'))  # Sort by total quantity
                .all()
            ]

            # Query for Battery Quantities
            battery_quantities = [
                {
                    "Item_Description": row.Item_Description,
                    "total_quantity": row.total_quantity
                }
                for row in db.session.query(
                    Items_List.Item_Description.label('Item_Description'),
                    func.sum(client_items.quantity).label('total_quantity')
                ).join(
                    client_items, or_(
                        client_items.item_description == Items_List.Item_Description,
                        client_items.item_description == Items_List.Alias_Description
                    )
                ).filter(
                    Items_List.Component == 'Batteries',
                    client_items.date.between(start_date, end_date)
                ).group_by(Items_List.Item_Description)
                .order_by(desc('total_quantity'))
                .all()
            ]

            # Query for Solar Panel Quantities
            solar_panel_quantities = [
                {
                    "Item_Description": row.Item_Description,
                    "total_quantity": row.total_quantity
                }
                for row in db.session.query(
                    Items_List.Item_Description.label('Item_Description'),
                    func.sum(client_items.quantity).label('total_quantity')
                ).join(
                    client_items, or_(
                        client_items.item_description == Items_List.Item_Description,
                        client_items.item_description == Items_List.Alias_Description
                    )
                ).filter(
                    Items_List.Component == 'Solar Panels',
                    client_items.date.between(start_date, end_date)
                ).group_by(Items_List.Item_Description)
                .order_by(desc('total_quantity'))
                .all()
            ]

            # Query for Victron Charge Controller Quantities
            victron_charge_controller_quantities = [
                {
                    "Item_Description": row.Item_Description,
                    "total_quantity": row.total_quantity
                }
                for row in db.session.query(
                    Items_List.Item_Description.label('Item_Description'),
                    func.sum(client_items.quantity).label('total_quantity')
                ).join(
                    client_items, or_(
                        client_items.item_description == Items_List.Item_Description,
                        client_items.item_description == Items_List.Alias_Description
                    )

                ).filter(
                    Items_List.Component == 'Victron Charge Controllers',
                    client_items.date.between(start_date, end_date)
                ).group_by(Items_List.Item_Description)
                .order_by(desc('total_quantity'))
                .all()
            ]



            # CTE to get the unique clients visited by each team member
            team_member_clients_query = db.session.query(
                Team_Members.Team_Member_Name,
                client_unique_days_query.columns.Client_Name,
                client_unique_days_query.columns.unique_days_at_client
            ).join(
                job_team_members, job_team_members.Team_Member_ID == Team_Members.Team_Member_ID
            ).join(
                Job_Tracking, Job_Tracking.Job_ID == job_team_members.Job_ID
            ).join(
                client_unique_days_query, Job_Tracking.Client_Name == client_unique_days_query.columns.Client_Name
            ).filter(
                Job_Tracking.Date.between(start_date, end_date)
            ).distinct().cte("team_member_clients")

            # CTE to calculate total unique days at clients per team member
            team_member_total_days_query = db.session.query(
                team_member_clients_query.columns.Team_Member_Name,
                func.sum(team_member_clients_query.columns.unique_days_at_client).label('total_days_at_clients')
            ).group_by(
                team_member_clients_query.columns.Team_Member_Name
            ).cte("team_member_total_days")

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
                days_worked_query.columns.days_worked,
                clients_visited_query.columns.clients_visited,
                team_member_total_days_query.columns.total_days_at_clients,
                (days_worked_query.columns.days_worked +
                 func.coalesce(clients_visited_query.columns.clients_visited, 0) /
                 func.coalesce(team_member_total_days_query.columns.total_days_at_clients, 1)
                ).label('ranking_score')
            ).join(days_worked_query, days_worked_query.columns.Team_Member_Name == Team_Members.Team_Member_Name) \
             .join(clients_visited_query, clients_visited_query.columns.Team_Member_Name == Team_Members.Team_Member_Name) \
             .outerjoin(team_member_total_days_query, team_member_total_days_query.columns.Team_Member_Name == Team_Members.Team_Member_Name) \
             .order_by(desc('ranking_score'))

            # Fetch the rankings
            team_rankings = ranking_query.all()

            if request.is_json:
                # Return JSON response for AJAX requests
                return jsonify({
                    "team_rankings": [
                        {
                            "Team_Member_Name": row.Team_Member_Name,
                            "days_worked": row.days_worked,
                            "clients_visited": row.clients_visited,
                            "total_days_at_clients": row.total_days_at_clients,
                            "ranking_score": row.ranking_score
                        } for row in team_rankings
                    ],
                    "client_days_data": [
                        {"Client_Name": row.Client_Name, "unique_days_at_client": row.unique_days_at_client}
                        for row in client_days_data
                    ],
                    "client_employee_days_data": [
                        {"Client_Name": row.Client_Name, "total_employee_days": row.total_employee_days}
                        for row in client_employee_days_data
                    ],
                    "inverter_data": [
                        {"Client_Name": row.Client_Name, "total_inverter_capacity": row.total_inverter_capacity}
                        for row in inverter_data
                    ],
                    "battery_data": [
                        {"Client_Name": row.Client_Name, "total_battery_capacity": row.total_battery_capacity}
                        for row in battery_data
                    ],
                    "solar_panel_data": [
                        {"Client_Name": row.Client_Name, "total_solar_panel_capacity": row.total_solar_panel_capacity}
                        for row in solar_panel_data
                    ],

                    "inverter_quantities": [
                        {"Item_Description": row.Item_Description, "total_quantity": row.total_quantity}
                        for row in inverter_quantities
                    ],
                    "battery_quantities": [
                        {"Item_Description": row.Item_Description, "total_quantity": row.total_quantity}
                        for row in battery_quantities
                    ],
                    "solar_panel_quantities": [
                        {"Item_Description": row.Item_Description, "total_quantity": row.total_quantity}
                        for row in solar_panel_quantities
                    ],

                    "victron_charge_controller_quantities": [
                        {"Item_Description": row.Item_Description, "total_quantity": row.total_quantity}
                        for row in victron_charge_controller_quantities
                    ]


                })
            # Render the team ranking page for form submissions
            return render_template(
                'team_ranking.html',
                team_rankings=team_rankings,
                client_days_data=client_days_data,
                client_employee_days_data=client_employee_days_data,  # Pass the new data
                inverter_data=inverter_data,
                battery_data=battery_data,
                solar_panel_data=solar_panel_data,
                inverter_quantities=inverter_quantities,
                battery_quantities=battery_quantities,
                solar_panel_quantities=solar_panel_quantities,
                victron_charge_controller_quantities=victron_charge_controller_quantities,
                start_date=start_date,
                end_date=end_date
            )

        # Render the team ranking page for GET requests
        return render_template('team_ranking.html', start_date=start_date, end_date=end_date)

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
from datetime import datetime

from flask import request, render_template  # Import request to check query parameters
from datetime import datetime, timedelta
from sqlalchemy import and_, func, text, or_
import logging

@app.route('/client_list', methods=['GET'])
def client_list():
    message = request.args.get('message', '')  # Retrieve the message from query params if available
    email_mode = request.args.get("email_mode", default=0, type=int)  # Check for email mode

    try:
        # Define the date threshold (14 months ago)
        fourteen_months_ago = datetime.utcnow() - timedelta(days=30 * 14)

        # Base query: Fetch all clients
        clients_query = db.session.query(Client_List).distinct()

        # If email_mode is active, filter clients based on the last 14 months using installation date
        if email_mode:
            clients_query = clients_query.join(
                client_items, or_(
                    client_items.client_name == Client_List.Client_Name,
                    client_items.client_name == Client_List.Alias_Name
                )
            ).filter(client_items.date >= fourteen_months_ago)

        # Execute the query
        clients = clients_query.all()

        # Query for Inverter data
        inverter_data = {
            row.Client_Name: {
                "total_inverter_capacity": round(row.total_inverter_capacity or 0, 2),
                "installed_by": row.installed_by
            }
            for row in db.session.query(
                func.max(text("Client_List.Client_Name")).label('Client_Name'),
                func.sum(client_items.quantity * Items_List.kVA_kW).label('total_inverter_capacity'),
                func.max(client_items.installed_by).label('installed_by')
            ).join(
                Items_List, or_(
                    client_items.item_description == Items_List.Item_Description,
                    client_items.item_description == Items_List.Alias_Description
                )
            ).join(
                Client_List, or_(
                    client_items.client_name == Client_List.Client_Name,
                    client_items.client_name == Client_List.Alias_Name
                )
            ).filter(client_items.component == 'Inverter').group_by(Client_List.Client_Name).all()
        }

        # Query for Battery data
        battery_data = {
            row.Client_Name: {
                "total_battery_capacity": round(row.total_battery_capacity or 0, 2),
                "installed_by": row.installed_by
            }
            for row in db.session.query(
                func.max(text("Client_List.Client_Name")).label('Client_Name'),
                func.sum(client_items.quantity * Items_List.kWh).label('total_battery_capacity'),
                func.max(client_items.installed_by).label('installed_by')
            ).join(
                Items_List, or_(
                    client_items.item_description == Items_List.Item_Description,
                    client_items.item_description == Items_List.Alias_Description
                )
            ).join(
                Client_List, or_(
                    client_items.client_name == Client_List.Client_Name,
                    client_items.client_name == Client_List.Alias_Name
                )
            ).filter(client_items.component == 'Batteries').group_by(Client_List.Client_Name).all()
        }

        # Query for Solar Panel data
        solar_panel_data = {
            row.Client_Name: {
                "total_solar_panel_capacity": round(row.total_solar_panel_capacity or 0, 3),
                "installed_by": row.installed_by
            }
            for row in db.session.query(
                func.max(text("Client_List.Client_Name")).label('Client_Name'),
                func.sum(client_items.quantity * Items_List.kVA_kW).label('total_solar_panel_capacity'),
                func.max(client_items.installed_by).label('installed_by')
            ).join(
                Items_List, or_(
                    client_items.item_description == Items_List.Item_Description,
                    client_items.item_description == Items_List.Alias_Description
                )
            ).join(
                Client_List, or_(
                    client_items.client_name == Client_List.Client_Name,
                    client_items.client_name == Client_List.Alias_Name
                )
            ).filter(client_items.component == 'Solar Panels').group_by(Client_List.Client_Name).all()
        }

        # Parse and format the latest invoice date
        installation_date_data = {
            row.Client_Name: (
                row.latest_installation_date.strftime('%d %B, %Y')
                if row.latest_installation_date else ''
            )
            for row in db.session.query(
                func.max(text("Client_List.Client_Name")).label('Client_Name'),
                func.max(client_items.date).label('latest_installation_date')
            ).join(
                Client_List, or_(
                    client_items.client_name == Client_List.Client_Name,
                    client_items.client_name == Client_List.Alias_Name
                )
            ).filter(client_items.component.in_(['Inverter', 'Batteries', 'Solar Panels'])).group_by(Client_List.Client_Name).all()
        }

        # Prepare the client lists
        tino_clients = []
        client_clients = []

        for client in clients:
            client_row = [
                client.Client_Unique_ID,
                client.Client_Name or '',
                client.Town or '',
                client.City or '',
                client.Phone_Number or '',
                client.Client_Code or '',
                client.Contact_Person or '',
                client.email_address or '',
                inverter_data.get(client.Client_Name, {}).get("total_inverter_capacity", ''),
                battery_data.get(client.Client_Name, {}).get("total_battery_capacity", ''),
                solar_panel_data.get(client.Client_Name, {}).get("total_solar_panel_capacity", ''),
                installation_date_data.get(client.Client_Name, ''),  # Invoice Date
                inverter_data.get(client.Client_Name, {}).get("installed_by", '') or
                battery_data.get(client.Client_Name, {}).get("installed_by", '') or
                solar_panel_data.get(client.Client_Name, {}).get("installed_by", '')
            ]

            # Categorize based on 'Installed By'
            if client_row[12] == 'Tino Team':
                tino_clients.append(client_row)
            elif client_row[12] == 'Client':
                client_clients.append(client_row)

        # Sort by Invoice Date (descending)
        tino_clients.sort(
            key=lambda x: datetime.strptime(x[11], '%d %B, %Y') if x[11] else datetime.min, reverse=True
        )
        client_clients.sort(
            key=lambda x: datetime.strptime(x[11], '%d %B, %Y') if x[11] else datetime.min, reverse=True
        )

        # Identify "Other Clients"
        tino_client_names = {row[1] for row in tino_clients}
        client_client_names = {row[1] for row in client_clients}
        all_categorized_names = tino_client_names.union(client_client_names)

        other_clients = [
            [
                client.Client_Unique_ID,
                client.Client_Name or '',
                client.Town or '',
                client.City or '',
                client.Phone_Number or '',
                client.Client_Code or '',
                client.Contact_Person or '',
                client.email_address or ''
            ]
            for client in clients if client.Client_Name not in all_categorized_names
        ]

    except Exception as e:
        logging.error(f"Error fetching clients: {e}")
        message = 'Database query failed'
        tino_clients = []
        client_clients = []
        other_clients = []

    return render_template(
        'client_list.html',
        tino_clients=tino_clients,
        client_clients=client_clients,
        other_clients=other_clients,
        message=message,
        static_url="/static/style.css"  # Pass static_url explicitly
    )


from collections import defaultdict




@app.route('/client_details/<client_id>')
def client_details(client_id):
    # Fetch client details using Client_Unique_ID
    client = db.session.query(Client_List).filter_by(Client_Unique_ID=client_id).first()
    if not client:
        return "Client not found", 404

    # Fetch team members for dropdown
    team_members = db.session.query(Team_Members).all()

    # Fetch the latest invoice date for the client
    installation_date_query = db.session.query(
        func.max(client_items.date).label('latest_installation_date')
    ).filter(
        or_(
            client_items.client_name == client.Client_Name,
            client_items.client_name == client.Alias_Name
        ),
        client_items.component.in_(['Inverter', 'Batteries', 'Solar Panels', 'Victron Charge Controllers'])
    ).first()

    installation_date = (
        installation_date_query.latest_installation_date.strftime('%d %B, %Y')
        if installation_date_query.latest_installation_date else 'No invoice date found'
    )

    # Format Start Date
    start_date = (
        client.start_date.strftime('%d %B, %Y')
        if client.start_date else 'No start date found'
    )

    # Format Commissioning Date
    commissioning_date = (
        client.commissioning_date.strftime('%d %B, %Y')
        if client.commissioning_date else 'No commissioning date found'
    )

    # Initialize component quantities
    component_quantities = {
        "Inverter": [],
        "Batteries": [],
        "Solar Panels": [],
        "Victron Charge Controllers": []
    }

    # Dictionary to track positive and negative quantities per item
    item_status = defaultdict(lambda: {"positive": [], "negative_count": 0})

    # Fetch components and number of solar panels from client_items
    try:
        for component_name, component_filter in {
            "Inverter": "Inverter",
            "Batteries": "Batteries",
            "Solar Panels": "Solar Panels",
            "Victron Charge Controllers": "Victron Charge Controllers"
        }.items():

            rows = db.session.query(
                client_items.client_item_id,
                client_items.item_description.label('Item_Description'),
                func.sum(client_items.quantity).label('total_quantity'),
                client_items.number_of_solar_panels
            ).filter(
                client_items.component == component_filter,
                or_(
                    client_items.client_name == client.Client_Name,
                    client_items.client_name == client.Alias_Name
                )
            ).group_by(client_items.client_item_id, client_items.item_description, client_items.number_of_solar_panels).all()

            if component_name == "Inverter":
                id_counter = 1  # Restoring original logic for Inverter IDs
                for row in rows:
                    total_quantity = int(row.total_quantity) if isinstance(row.total_quantity, decimal.Decimal) else row.total_quantity
                    is_negative = total_quantity < 0

                    if is_negative:
                        item_status[(component_name, row.Item_Description)]["negative_count"] += abs(total_quantity)
                        continue  # Skip negative items

                    solar_panels_list = str(row.number_of_solar_panels).split() if row.number_of_solar_panels else [""]

                    for i in range(abs(total_quantity)):  # Use absolute value
                        solar_panel_value = solar_panels_list[i] if i < len(solar_panels_list) else ""

                        item_entry = {
                            "Item_Description": row.Item_Description,
                            "total_quantity": total_quantity,  # Store original value
                            "Inverter_ID": f"Inverter {id_counter}",  # Restore original Inverter ID logic
                            "Number_of_Solar_Panels": solar_panel_value,  # Assign individual values
                            "Client_Item_ID": row.client_item_id,  # Store ID for updating later
                            "negative_quantity": False  # Default as positive
                        }
                        item_status[(component_name, row.Item_Description)]["positive"].append(item_entry)
                        id_counter += 1  # Increment Inverter ID counter

            elif component_name == "Victron Charge Controllers":
                id_counter = 1  # Restoring original logic for Controller IDs
                for row in rows:
                    total_quantity = int(row.total_quantity) if isinstance(row.total_quantity, decimal.Decimal) else row.total_quantity
                    is_negative = total_quantity < 0

                    if is_negative:
                        item_status[(component_name, row.Item_Description)]["negative_count"] += abs(total_quantity)
                        continue  # Skip negative items

                    solar_panels_list = str(row.number_of_solar_panels).split() if row.number_of_solar_panels else [""]

                    for i in range(abs(total_quantity)):  # Use absolute value
                        solar_panel_value = solar_panels_list[i] if i < len(solar_panels_list) else ""

                        item_entry = {
                            "Item_Description": row.Item_Description,
                            "total_quantity": total_quantity,  # Store original value
                            "Controller_ID": f"Controller {id_counter}",  # Restore original Controller ID logic
                            "Number_of_Solar_Panels": solar_panel_value,  # Assign individual values
                            "Client_Item_ID": row.client_item_id,  # Store ID for updating later
                            "negative_quantity": False  # Default as positive
                        }
                        item_status[(component_name, row.Item_Description)]["positive"].append(item_entry)
                        id_counter += 1  # Increment Controller ID counter

            else:  # Batteries & Solar Panels (No Strikethrough, No Omission)
                for row in rows:
                    total_quantity = int(row.total_quantity) if isinstance(row.total_quantity, decimal.Decimal) else row.total_quantity

                    item_entry = {
                        "Item_Description": row.Item_Description,
                        "total_quantity": total_quantity,
                        "Client_Item_ID": row.client_item_id,  # Store ID for reference
                        "negative_quantity": total_quantity < 0  # Mark negative values
                    }
                    item_status[(component_name, row.Item_Description)]["positive"].append(item_entry)

    except Exception as e:
        logging.error(f"Error fetching component quantities for client {client.Client_Name}: {e}")
        return "An error occurred while fetching component details.", 500

    # Apply strikethrough **only** for Inverters & Victron Charge Controllers
    for (component, description), status in item_status.items():
        if component in ["Inverter", "Victron Charge Controllers"]:
            num_negative = status["negative_count"]
            positive_items = status["positive"]

            for i in range(min(num_negative, len(positive_items))):
                positive_items[i]["negative_quantity"] = True  # Mark for strikethrough

        component_quantities[component].extend(status["positive"])  # Add all items
    print(f"Client Sales Person: {client.sales_person}")

    # Render the template with the updated component_quantities
    return render_template(
        'client_details.html',
        client=client,
        installation_date=installation_date,
        start_date=start_date,
        commissioning_date=commissioning_date,
        team_members=team_members,  # Pass team members to template
        inverter_quantities=component_quantities["Inverter"],
        battery_quantities=component_quantities["Batteries"],
        solar_panel_quantities=component_quantities["Solar Panels"],
        victron_charge_controller_quantities=component_quantities["Victron Charge Controllers"]
    )



@app.route('/save_client_comment/<client_id>', methods=['POST'])
def save_client_comment(client_id):
    client = db.session.query(Client_List).filter_by(Client_Unique_ID=client_id).first()
    if not client:
        return "Client not found", 404

    # Print form values for debugging
    print("Received Form Data:", request.form)

    # Get values from form
    general_comment = request.form.get('general_comment', '')
    sales_person = request.form.get('sales_person', '')
    lead_installer = request.form.get('lead_installer', '')
    start_date = request.form.get('start_date', None)
    commissioning_date = request.form.get('commissioning_date', None)

    # Print extracted values
    print(f"General Comment: {general_comment}")
    print(f"Sales Person: {sales_person}")
    print(f"Lead Installer: {lead_installer}")
    print(f"Start Date: {start_date}")
    print(f"Commissioning Date: {commissioning_date}")

    # Update client details
    client.general_comment = general_comment
    #client.sales_person = sales_person if sales_person else None
    if sales_person.strip():
        client.sales_person = sales_person.strip()
    else:
        client.sales_person = None
    #client.lead_installer = lead_installer if lead_installer else None
    if lead_installer.strip():
        client.lead_installer = lead_installer.strip()
    else:
        client.lead_installer = None
    client.start_date = start_date if start_date else None
    client.commissioning_date = commissioning_date if commissioning_date else None
    client.google_location = request.form.get("google_location", "").strip()  # Update Google Location

    try:
        # Fetch all inverter records for this client, ordered by client_item_id
        inverter_items = db.session.query(client_items).filter(
            client_items.component == "Inverter",
            or_(
                client_items.client_name == client.Client_Name,
                client_items.client_name == client.Alias_Name
            )
        ).order_by(client_items.client_item_id).all()

        # Fetch all Victron Charge Controller records for this client, ordered by client_item_id
        victron_items = db.session.query(client_items).filter(
            client_items.component == "Victron Charge Controllers",
            or_(
                client_items.client_name == client.Client_Name,
                client_items.client_name == client.Alias_Name
            )
        ).order_by(client_items.client_item_id).all()

        # Dictionaries to store updates
        inverter_updates = {}
        victron_updates = {}

        # Process the form inputs
        for key, value in request.form.items():
            if key.startswith("number_of_solar_panels_") and not key.startswith("number_of_solar_panels_victron_"):
                index = int(key.split("_")[-1]) - 1
                number_of_solar_panels_value = str(value).strip() if str(value).strip().isdigit() else ""

                client_item_id = request.form.get(f"client_item_id_{index + 1}")
                if client_item_id:
                    if client_item_id not in inverter_updates:
                        inverter_updates[client_item_id] = []
                    inverter_updates[client_item_id].append(number_of_solar_panels_value)

            elif key.startswith("number_of_solar_panels_victron_"):
                index = int(key.split("_")[-1]) - 1
                number_of_solar_panels_value = str(value).strip() if str(value).strip().isdigit() else ""

                client_item_id = request.form.get(f"client_item_id_victron_{index + 1}")
                if client_item_id:
                    if client_item_id not in victron_updates:
                        victron_updates[client_item_id] = []
                    victron_updates[client_item_id].append(number_of_solar_panels_value)

        # Apply updates for inverters
        for inverter_item in inverter_items:
            if str(inverter_item.client_item_id) in inverter_updates:
                existing_values = inverter_item.number_of_solar_panels.split() if inverter_item.number_of_solar_panels else []
                total_quantity = int(inverter_item.quantity) if inverter_item.quantity else 0

                while len(existing_values) < total_quantity:
                    existing_values.append("")

                updates_for_item = inverter_updates[str(inverter_item.client_item_id)]
                for i, update_value in enumerate(updates_for_item):
                    if i < len(existing_values):
                        existing_values[i] = update_value

                inverter_item.number_of_solar_panels = ' '.join(existing_values)

        # Apply updates for Victron Charge Controllers
        for victron_item in victron_items:
            if str(victron_item.client_item_id) in victron_updates:
                existing_values = victron_item.number_of_solar_panels.split() if victron_item.number_of_solar_panels else []
                total_quantity = int(victron_item.quantity) if victron_item.quantity else 0

                while len(existing_values) < total_quantity:
                    existing_values.append("")

                updates_for_item = victron_updates[str(victron_item.client_item_id)]
                for i, update_value in enumerate(updates_for_item):
                    if i < len(existing_values):
                        existing_values[i] = update_value

                victron_item.number_of_solar_panels = ' '.join(existing_values)

        db.session.commit()
        flash("Client details and comments saved successfully!", "success")
    except Exception as e:
        db.session.rollback()
        print(f"Database Commit Error: {e}")  # Print the actual error
        logging.error(f"Error saving data for client {client.Client_Name}: {e}")
        flash("An error occurred while saving the data.", "danger")

    return redirect(url_for('client_details', client_id=client_id))







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
                        item = Items_List(
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

from sqlalchemy import text

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

            if filter_type == 'date' and start_date and end_date:
                conditions.append(Job_Tracking.Date.between(start_date, end_date))

            if filter_type == 'both' and team_member_name and start_date and end_date:
                # Combine both conditions
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
                func.max(text("Client_List.Client_Name")).label('Client_Name'),
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





from urllib.parse import unquote
@app.route('/get_remaining_stock/<path:item_name>', methods=['GET'])
def get_remaining_stock(item_name):
    item_name_decoded = unquote(item_name)
    app.logger.info(f"Received item_name: {item_name}")
    app.logger.info(f"Decoded item_name: {item_name_decoded}")

    try:
        # Perform database query
        item = Items_List.query.filter_by(Item_Description=item_name_decoded).first()
        if item:
            app.logger.info(f"Item found: {item.Item_Description}, Quantity: {item.Quantity}")
            return jsonify({
                "Item_Description": item.Item_Description,
                "Quantity": item.Quantity
            }), 200
        else:
            app.logger.warning(f"Item not found in the database for '{item_name_decoded}'")
            return jsonify({"error": f"Item '{item_name_decoded}' not found"}), 404
    except Exception as e:
        app.logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_components', methods=['GET'])
def get_components():
    try:
        components = db.session.query(Items_List.Component).distinct().filter(Items_List.Component.isnot(None)).all()
        components_list = [component[0] for component in components]
        return jsonify(components_list)
    except Exception as e:
        print("Error in /get_components:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/get_item_descriptions/<component>', methods=['GET'])
def get_item_descriptions(component):
    try:
        item_descriptions = (
            db.session.query(Items_List.Item_Description)
            .filter(Items_List.Component == component)
            .distinct()
            .all()
        )
        descriptions_list = [desc[0] for desc in item_descriptions]
        return jsonify(descriptions_list)
    except Exception as e:
        print("Error in /get_item_descriptions:", str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/submit_component', methods=['POST'])
def submit_component():
    try:
        app.logger.info("Processing /submit_component request...")

        data = request.get_json()
        app.logger.info(f"Received data: {data}")

        client_name = data.get('client_name')
        date = data.get('date')
        installed_by = data.get('installed_by')
        items = data.get('items')

        if not client_name or not date or not installed_by or not items:
            app.logger.warning("Missing required fields: client_name, date, installed_by, or items.")
            return jsonify({"error": "Client name, date, installed by, and items are required."}), 400

        valid_installers = ["Tino Team", "Client"]
        if installed_by not in valid_installers:
            app.logger.warning(f"Invalid 'Installed By' value: {installed_by}")
            return jsonify({"error": f"'Installed By' must be one of {valid_installers}."}), 400

        from datetime import datetime
        try:
            date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            app.logger.warning(f"Invalid date format: {date}")
            return jsonify({"error": "Date must be in YYYY-MM-DD format."}), 400

        app.logger.info(f"Client: {client_name}, Date: {date}, Installed By: {installed_by}, Items: {items}")

        for item in items:
            component = item.get('component')
            item_description = item.get('item_description')
            quantity = item.get('quantity')

            if not component or not item_description or not quantity:
                app.logger.warning(f"Missing required fields in item: {item}")
                return jsonify({"error": "Each item must include component, item_description, and quantity."}), 400

            try:
                quantity = int(quantity)
            except ValueError:
                app.logger.warning(f"Invalid quantity for item: {item}")
                return jsonify({"error": "Quantity must be a valid integer."}), 400

            stock_item = Items_List.query.filter_by(Item_Description=item_description).first()
            if not stock_item:
                app.logger.warning(f"Item not found: {item_description}")
                return jsonify({"error": f"Item '{item_description}' not found in stock."}), 400

            if stock_item.Quantity < quantity:
                app.logger.warning(f"Insufficient stock for {item_description}. Requested: {quantity}, Available: {stock_item.Quantity}")
                return jsonify({"error": f"Not enough stock for '{item_description}'. Available: {stock_item.Quantity}."}), 400

            stock_item.Quantity -= quantity
            app.logger.info(f"Stock updated for {item_description}. New quantity: {stock_item.Quantity}")

            new_entry = client_items(
                client_name=client_name,
                date=date,
                component=component,
                item_description=item_description,
                quantity=quantity,
                installed_by=installed_by
            )
            db.session.add(new_entry)

        db.session.commit()
        app.logger.info("All items added successfully. Transaction committed.")

        return jsonify({"message": "Data submitted and stock updated successfully."}), 200

    except Exception as e:
        db.session.rollback()
        import uuid
        error_id = str(uuid.uuid4())
        app.logger.error(f"Error ID {error_id}: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred. Reference ID: {error_id}"}), 500

@app.route('/stock_disbursement', methods=['GET'])
def stock_disbursement():
    """Render the stock disbursement page."""
    return render_template('stock_disbursement.html')

@app.route('/update_stock', methods=['POST'])
def update_stock():
    """
    Update the Quantity in the Items_List table by subtracting the corresponding quantity
    in the client_items table for matching item_description values.
    """
    try:
        # Log the start of the request
        app.logger.info("Processing /update_stock request...")

        # Execute the SQL query to update stock
        db.session.execute(
            text("""
                UPDATE Items_List AS il
                JOIN client_items AS ci
                ON il.Item_Description = ci.item_description
                SET il.Quantity = il.Quantity - ci.quantity
                WHERE il.Quantity >= ci.quantity;
            """)
        )

        # Commit the changes
        db.session.commit()
        app.logger.info("Stock updated successfully.")

        return jsonify({"message": "Stock updated successfully."}), 200

    except SQLAlchemyError as e:
        # Rollback the session in case of an error
        db.session.rollback()
        import uuid
        error_id = str(uuid.uuid4())
        app.logger.error(f"Error ID {error_id}: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred. Reference ID: {error_id}"}), 500





@app.route('/stock_summary', methods=['GET', 'POST'])
def stock_summary():
    try:
        # Initialize variables for form data
        filter_type = ''
        item_description = ''
        start_date = ''
        end_date = ''
        group_by = 'Item_Description'  # Default grouping by Item Description
        installed_by_values = []  # New filter for multiple Installed By values

        # Fetch item descriptions for autocomplete (include Alias_Description)
        item_descriptions = [
            item.Item_Description for item in Items_List.query.all()
        ] + [
            item.Alias_Description for item in Items_List.query.all() if item.Alias_Description
        ]

        # Initialize capacity variables
        panel_capacity = 0
        inverter_capacity = 0
        battery_capacity = 0

        if request.method == 'POST':
            # Get the form data
            filter_type = request.form.get('filter_type', '')
            item_description = request.form.get('item_description', '')
            start_date = request.form.get('start_date', '')
            end_date = request.form.get('end_date', '')
            group_by = request.form.get('group_by', 'Item_Description')
            installed_by_values = request.form.getlist('installed_by')  # Fetch multiple values

            logging.debug(f"Filter Type: {filter_type}")
            logging.debug(f"Item Description: {item_description}")
            logging.debug(f"Start Date: {start_date}")
            logging.debug(f"End Date: {end_date}")
            logging.debug(f"Group By: {group_by}")
            logging.debug(f"Installed By: {installed_by_values}")

            conditions = []

            # Filtering based on the filter type
            if filter_type in ['item_description', 'both'] and item_description:
                conditions.append(
                    or_(
                        client_items.item_description == item_description,
                        client_items.item_description == Items_List.Alias_Description
                    )
                )

            if filter_type in ['date', 'both'] and start_date and end_date:
                conditions.append(client_items.date.between(start_date, end_date))

            if installed_by_values:  # Multiple values for Installed By
                conditions.append(client_items.installed_by.in_(installed_by_values))

            # Avoid empty `and_()` warning
            condition_clause = and_(*conditions) if conditions else true()

            # Handle grouping
            group_column_map = {
                "Client_Name": Client_List.Client_Name,
                "Item_Description": client_items.item_description,
                "Date": client_items.date
            }

            group_column = group_column_map.get(group_by, client_items.item_description)

            # Query to get the client-item details with proper component mapping from Items_List
            jobs_query = db.session.query(
                client_items.client_item_id,
                func.max(text("Client_List.Client_Name")).label('Client_Name'),
                client_items.date,
                func.max(Items_List.Component).label('Component'),
                func.max(Items_List.Item_Description).label('Item_Description'),
                func.max(client_items.quantity).label('Quantity'),
                func.max(client_items.installed_by).label('Installed_By'),
                func.max(Client_List.Alias_Name).label('Alias_Name'),
            ).join(
                Items_List, or_(
                    client_items.item_description == Items_List.Item_Description,
                    client_items.item_description == Items_List.Alias_Description
                )
            ).join(
                Client_List,
                or_(
                    client_items.client_name == Client_List.Client_Name,
                    client_items.client_name == Client_List.Alias_Name
                )
            ).filter(
                condition_clause
            ).group_by(
                client_items.client_item_id, group_column
            ).order_by(
                client_items.date.desc()
            )

            jobs = jobs_query.all()

            # Group jobs by selected group_by option
            grouped_jobs = {}
            for job in jobs:
                group_key = {
                    "Client_Name": job.Client_Name,
                    "Item_Description": job.Item_Description,
                    "Date": job.date
                }.get(group_by, job.Item_Description)
                grouped_jobs.setdefault(group_key, []).append(job)

            # Calculate capacities based on the filtered data from jobs_query
            job_items = db.session.query(
                Items_List.Item_Description,
                Items_List.Component,
                client_items.quantity,
                Items_List.kVA_kW,
                Items_List.kWh
            ).join(
                client_items, or_(
                    Items_List.Item_Description == client_items.item_description,
                    Items_List.Alias_Description == client_items.item_description
                )
            ).join(
                Client_List, or_(
                    client_items.client_name == Client_List.Client_Name,
                    client_items.client_name == Client_List.Alias_Name
                )
            ).filter(
                condition_clause
            ).all()

            # Initialize capacities
            panel_capacity = 0
            inverter_capacity = 0
            battery_capacity = 0

            # Calculate capacities with type conversion
            for item in job_items:
                try:
                    quantity = int(item.quantity or 0)
                    kVA_kW = float(item.kVA_kW or 0)
                    kWh = float(item.kWh or 0)

                    if item.Component == "Solar Panels":
                        panel_capacity += kVA_kW * quantity
                    elif item.Component == "Inverter":
                        inverter_capacity += kVA_kW * quantity
                    elif item.Component == "Batteries":
                        battery_capacity += kWh * quantity
                except ValueError as ve:
                    logging.warning(f"Skipping item due to type error: {ve}")

            # Round off the capacities to 2 decimal places
            panel_capacity = round(panel_capacity, 2)
            inverter_capacity = round(inverter_capacity, 2)
            battery_capacity = round(battery_capacity, 2)


        # Render the template
        return render_template(
            'stock_summary.html',
            grouped_jobs=grouped_jobs if request.method == 'POST' else {},
            item_descriptions=item_descriptions,
            filter_type=filter_type,
            item_description=item_description,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            installed_by_values=installed_by_values,
            panel_capacity=panel_capacity,
            inverter_capacity=inverter_capacity,
            battery_capacity=battery_capacity
        )

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error occurred: {e}")
        return str(e)

    finally:
        db.session.close()


@app.route('/autocomplete_item_description', methods=['GET'])
def autocomplete_item_description():
    search_term = request.args.get('query', '')
    if not search_term:
        return jsonify([])  # Return an empty list if no search term provided

    # Query database for matching Item_Description values
    matches = (
        Items_List.query.filter(Items_List.Item_Description.ilike(f"%{search_term}%"))
        .limit(10)  # Limit results to 10 to avoid overloading
        .all()
    )

    # Return JSON response with matching descriptions
    return jsonify([item.Item_Description for item in matches])




from sqlalchemy.sql import text  # Ensure this import is included

@app.route('/upload_sales', methods=['GET', 'POST'])
def upload_sales():
    if request.method == 'POST':
        file = request.files['file']
        if file:
            try:
                # Load the Excel file
                df = pd.read_excel(file, header=11)  # Read from row 12 (0-indexed)
                data = []
                current_item_description = None

                # Load mapping of Alias_Description to Item_Description from Items_List table
                engine = db.engine
                with engine.begin() as conn:
                    alias_to_description = dict(conn.execute(text("""
                        SELECT Alias_Description, Item_Description FROM Items_List
                    """)).fetchall())

                # Process rows to extract Item Description and other fields
                for _, row in df.iterrows():
                    date_value = row['Date']
                    document_no = row['Document No.']
                    customer = row['Customer']
                    qty_sold = row['Qty Sold']

                    # Determine if the row is an item description
                    if pd.notnull(date_value) and pd.isnull(document_no) and pd.isnull(customer) and pd.isnull(qty_sold):
                        current_item_description = str(date_value)  # Treat 'Date' column as item description
                        continue

                    # Skip rows with 'Total for' or 'Grand Total'
                    if isinstance(date_value, str) and (date_value.startswith("Total for") or date_value.startswith("Grand Total")):
                        continue

                    # Map the item description using the Alias_Description mapping
                    mapped_item_description = alias_to_description.get(current_item_description, current_item_description)

                    # Add regular sales rows
                    if pd.notnull(date_value):
                        data.append({
                            "item_description": mapped_item_description,  # Use the mapped description
                            "date": pd.to_datetime(date_value).date() if not pd.isnull(date_value) else None,
                            "document_no": document_no,
                            "customer": customer,
                            "qty_sold": qty_sold
                        })

                # Insert into MySQL with ON DUPLICATE KEY UPDATE
                if data:
                    with engine.begin() as conn:
                        insert_query = """
                        INSERT INTO sales_by_item (item_description, date, document_no, customer, qty_sold)
                        VALUES (:item_description, :date, :document_no, :customer, :qty_sold)
                        ON DUPLICATE KEY UPDATE
                            qty_sold = VALUES(qty_sold);  -- Update logic if needed
                        """
                        conn.execute(text(insert_query), data)

                flash("Sales data uploaded successfully!", "success")
            except SQLAlchemyError as e:
                flash(f"Error saving to database: {str(e)}", "danger")
            except Exception as e:
                flash(f"Error processing file: {str(e)}", "danger")
            return redirect(url_for('upload_sales'))

    return render_template('upload_sales.html')

@app.template_filter('serialize_row')
def serialize_row(row):
    try:
        return row._asdict()  # For SQLAlchemy Row or namedtuples
    except AttributeError:
        return dict(row)  # Fallback for other iterable key-value pairs


from celery_worker import update_folder_has_files  # 👈 make sure this import is at the top

from flask import request, render_template
from datetime import datetime, timedelta
import logging

@app.route('/projects', methods=['GET'])
def get_projects():
    message = request.args.get('message', '')

    # Retrieve filter values from request arguments
    start_date_from = request.args.get('start_date_from', '')
    start_date_to = request.args.get('start_date_to', '')
    search_query = request.args.get('search_query', '').strip().lower()  # Get the search input

    try:
        # Base query
        query = db.session.query(
            projects.project_id,
            projects.client_name,
            projects.town,
            projects.phone_number,
            projects.sales_person,
            projects.lead_installer,
            projects.start_date,
            projects.commissioning_date,
            projects.invoice_image_url,
            projects.google_coordinates,
            projects.currency,
            projects.invoice_amount,
            projects.amount_paid,
            projects.outstanding_balance,
            projects.expected_final_payment_date,
            projects.comment,
            projects.folder_has_files,  # <-- Add this line
            projects.google_folder_id  # <-- add this line
        ).distinct()

        # Apply date filters if provided
        if start_date_from:
            start_date_from = datetime.strptime(start_date_from, '%Y-%m-%d')
            query = query.filter(projects.start_date >= start_date_from)

        if start_date_to:
            start_date_to = datetime.strptime(start_date_to, '%Y-%m-%d')
            query = query.filter(projects.start_date <= start_date_to)

        # Apply search filter
        if search_query:
            query = query.filter(
                (projects.client_name.ilike(f"%{search_query}%")) |
                (projects.town.ilike(f"%{search_query}%")) |
                (projects.phone_number.ilike(f"%{search_query}%")) |
                (projects.sales_person.ilike(f"%{search_query}%")) |
                (projects.lead_installer.ilike(f"%{search_query}%"))
            )

        # Execute the filtered query
        projects_list = query.all()

        # Fetch team members
        team_members = db.session.query(Team_Members.Team_Member_Name).all()
        team_members = [member.Team_Member_Name for member in team_members]

        new_projects = []
        ongoing_projects = []
        completed_projects = []


        for project in projects_list:
            def format_date(date_value):
                if date_value in [None, "0000-00-00"]:
                    return ""
                if isinstance(date_value, (datetime, date)):
                    return date_value.strftime('%Y-%m-%d')
                return date_value

            start_date = format_date(project.start_date)
            commissioning_date = format_date(project.commissioning_date)
            expected_payment_date = format_date(project.expected_final_payment_date)

            folder_name = f"{project.client_name}_{project.town}_{project.sales_person}_{project.project_id}"

            folder_id = project.google_folder_id  # Ensure this attribute exists

            # Only trigger Celery task if folder hasn't been checked yet (None or False)
            should_check_folder = folder_id and (project.folder_has_files is None or project.folder_has_files == 0)

            if should_check_folder:
                update_folder_has_files.delay(project.project_id, folder_id)

            # Only show link if folder_has_files is True
            folder_link = f"https://drive.google.com/drive/folders/{folder_id}" if project.folder_has_files else ""

            project_data = {
                "project_id": project.project_id,
                "client_name": project.client_name or '',
                "town": project.town or '',
                "phone_number": project.phone_number or '',
                "sales_person": project.sales_person or '',
                "lead_installer": project.lead_installer or '',
                "start_date": start_date,
                "commissioning_date": commissioning_date,
                "invoice_image_url": project.invoice_image_url or '',
                "folder_id": folder_id,
                "folder_link": folder_link,
                "google_coordinates": project.google_coordinates or '',
                "currency": project.currency or '',
                "invoice_amount": project.invoice_amount or 0.00,
                "amount_paid": project.amount_paid or 0.00,
                "outstanding_balance": project.outstanding_balance or 0.00,
                "expected_final_payment_date": expected_payment_date,
                "comment": project.comment or ''
            }

            # Categorize
            if project_data["client_name"] and project_data["town"] and project_data["sales_person"] and not project_data["lead_installer"] and not project_data["start_date"] and not project_data["commissioning_date"]:
                new_projects.append(project_data)
            elif project_data["commissioning_date"] and project_data["start_date"]:
                completed_projects.append(project_data)
            elif project_data["lead_installer"] and project_data["start_date"]:
                ongoing_projects.append(project_data)

        # Sort Ongoing Projects by most recent Start Date
        ongoing_projects.sort(key=lambda x: x["start_date"], reverse=True)

        # Sort Completed Projects by most recent Commissioning Date
        completed_projects.sort(key=lambda x: x["commissioning_date"], reverse=True)

        return render_template(
            'projects.html',
            new_projects=new_projects,
            ongoing_projects=ongoing_projects,
            completed_projects=completed_projects,
            team_members=team_members,
            message=message,
            search_query=search_query,  # Pass search term back to template
            start_date_from=start_date_from,
            start_date_to=start_date_to
        )

    except Exception as e:
        logging.error(f"Error fetching projects: {e}")
        return render_template('projects.html', message='Database query failed', new_projects=[], ongoing_projects=[], completed_projects=[], team_members=[])



@app.route('/update_projects', methods=['POST'])
def update_projects():
    try:
        data = request.json.get('projects', [])
        ongoing_projects = []  # Track projects that just moved to "Ongoing"
        completed_projects = []  # Track projects that just moved to "Completed"

        for project in data:
            project_id = project.get('project_id')

            if project_id:  # Updating an existing project
                existing_project = db.session.query(projects).filter_by(project_id=project_id).first()
                if existing_project:
                    # Preserve existing values if not provided in the request
                    project_fields = {
                        'client_name': project.get('client_name', existing_project.client_name),
                        'town': project.get('town', existing_project.town),
                        'phone_number': project.get('phone_number', existing_project.phone_number),
                        'sales_person': project.get('sales_person') if 'sales_person' in project else existing_project.sales_person,
                        #'sales_person': project.get('sales_person', existing_project.sales_person) if project.get('sales_person') else existing_project.sales_person,
                        'lead_installer': project.get('lead_installer') if 'lead_installer' in project else existing_project.lead_installer,
                        #'lead_installer': project.get('lead_installer', existing_project.lead_installer) if project.get('lead_installer') else existing_project.lead_installer,
                        'start_date': project.get('start_date', existing_project.start_date),
                        #'start_date': project.get('start_date', existing_project.start_date) if project.get('start_date') else existing_project.start_date,
                        'commissioning_date': project.get('commissioning_date', existing_project.commissioning_date),
                        #'commissioning_date': project.get('commissioning_date', existing_project.commissioning_date) if project.get('commissioning_date') else existing_project.commissioning_date,
                        'invoice_image_url': project.get('invoice_image_url', existing_project.invoice_image_url),
                        'google_coordinates': project.get('google_coordinates', existing_project.google_coordinates),
                        'currency': project.get('currency', existing_project.currency),
                        'invoice_amount': project.get('invoice_amount', existing_project.invoice_amount),
                        'amount_paid': project.get('amount_paid', existing_project.amount_paid),
                        'outstanding_balance': project.get('outstanding_balance', existing_project.outstanding_balance),
                        'expected_final_payment_date': project.get('expected_final_payment_date', existing_project.expected_final_payment_date),
                        'comment': project.get('comment', existing_project.comment),
                    }

                    # Track previous statuses before changes
                    previously_ongoing = bool(existing_project.lead_installer and existing_project.start_date)
                    previously_completed = existing_project.commissioning_date not in [None, "0000-00-00"]

                    # Apply updates to the existing project
                    for key, value in project_fields.items():
                        setattr(existing_project, key, value)

                    # Check if project just moved to "Ongoing"
                    if not previously_ongoing and existing_project.lead_installer and existing_project.start_date:
                        ongoing_projects.append(existing_project)

                    # Check if project just moved to "Completed"
                    if not previously_completed and existing_project.commissioning_date:
                        completed_projects.append(existing_project)

            else:  # Adding a new project
                new_project = projects(
                    client_name=project.get('client_name', ''),
                    town=project.get('town', ''),
                    phone_number=project.get('phone_number', ''),
                    sales_person=project.get('sales_person', ''),
                    lead_installer=project.get('lead_installer', ''),
                    start_date=project.get('start_date', None),
                    commissioning_date=project.get('commissioning_date', None),
                    invoice_image_url=project.get('invoice_image_url', ''),
                    google_coordinates=project.get('google_coordinates', ''),
                    currency=project.get('currency', ''),
                    invoice_amount=project.get('invoice_amount', 0.00),
                    amount_paid=project.get('amount_paid', 0.00),
                    outstanding_balance=project.get('outstanding_balance', 0.00),
                    expected_final_payment_date=project.get('expected_final_payment_date', None),
                    comment=project.get('comment', '')
                )
                db.session.add(new_project)

                if new_project.lead_installer and new_project.start_date:
                    ongoing_projects.append(new_project)

                if new_project.commissioning_date:
                    completed_projects.append(new_project)

        db.session.commit()

        # Send email notifications only for projects that changed status
        for project in ongoing_projects:
            send_project_email_notification(project)

        for project in completed_projects:
            send_completed_project_email_notification(project)

        return jsonify({"message": "Projects updated successfully"})

    except Exception as e:
        logging.error(f"Error updating projects: {e}")
        return jsonify({"message": "Error updating projects"}), 500


def format_date_with_suffix(date_obj):
    if not date_obj:
        return "N/A"
    suffix = lambda d: "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    return date_obj.strftime(f"%A, %-d{suffix(date_obj.day)} %B, %Y")


def send_project_email_notification(project):
    """Sends an email notification to the sales person when their project becomes ongoing."""
    with app.app_context():
        sales_person_email = db.session.query(Team_Members.Team_Member_Email).filter(
            Team_Members.Team_Member_Name == project.sales_person
        ).scalar()

        if not sales_person_email:
            print(f"ERROR: No email found for sales person {project.sales_person}")
            return

        # Generate Google Maps link if coordinates exist
        google_maps_link = f'<p><b>Location:</b> <a href="https://www.google.com/maps?q={project.google_coordinates}" target="_blank">View on Google Maps</a></p>' if project.google_coordinates else ""

        invoice_link = f'<p><b>Invoice:</b> <a href="{project.invoice_image_url}" target="_blank">View Invoice</a></p>' if project.invoice_image_url else ""

        # Check if project folder contains files before adding the Google Drive link
        google_drive_link = (
            f'<p><b>Project Pictures:</b> <a href="https://drive.google.com/drive/folders/{project.google_folder_id}" target="_blank">View Files</a></p>'
            if project.google_folder_id and folder_has_files(project.google_folder_id) else ""
        )

        subject = f"Project Update: {project.client_name} installation is now Ongoing"

        body = f"""
        <p>Dear {project.sales_person},</p>
        <p>Your installation for <b>{project.client_name}</b> in <b>{project.town}</b> has now moved to the <b>Ongoing</b> stage.</p>
        <p><b>Project Details:</b></p>
        <ul>
            <li>Client Name: {project.client_name}</li>
            <li>Town: {project.town}</li>
            <li>Start Date: {format_date_with_suffix(project.start_date)}</li>
            <li>Lead Installer: {project.lead_installer}</li>
        </ul>
        {google_maps_link}
        {invoice_link}
        {google_drive_link}
        <p>You can check the status of other projects by clicking <a href="https://tino-solutions-reports-49ba7768c4e2.herokuapp.com/projects" target="_blank">here</a>.</p>
        <p>Kind regards,<br>Emmanuel Kwesi Padi</p>
        """
        #<hr>
        #<p style="font-size: 12px; color: gray;">This email was automatically generated from the Tino Solutions System Database.</p>

        msg = Message(
            subject,
            #recipients=["emmanuel@tinosolutions.com"],
            recipients=[sales_person_email],
            #cc=["emmanuel@tinosolutions.com"],
            cc=["augustine@tinosolutions.com"],
            bcc=["ebenezer@tinosolutions.com", "emmanuel@tinosolutions.com"],  # Add BCC recipients
            html=body
        )

        try:
            mail.send(msg)
            print(f"Email sent to {sales_person_email} for project {project.client_name}")
        except Exception as e:
            print(f"ERROR: Failed to send email to {sales_person_email}: {e}")

def send_completed_project_email_notification(project):
    """Sends an email notification when a project moves to Completed status."""
    with app.app_context():
        sales_person_email = db.session.query(Team_Members.Team_Member_Email).filter(
            Team_Members.Team_Member_Name == project.sales_person
        ).scalar()

        if not sales_person_email:
            print(f"ERROR: No email found for sales person {project.sales_person}")
            return

        # Generate Google Maps link if coordinates exist
        google_maps_link = f'<p><b>Location:</b> <a href="https://www.google.com/maps?q={project.google_coordinates}" target="_blank">View on Google Maps</a></p>' if project.google_coordinates else ""

        invoice_link = f'<p><b>Invoice:</b> <a href="{project.invoice_image_url}" target="_blank">View Invoice</a></p>' if project.invoice_image_url else ""

        # Check if project folder contains files before adding the Google Drive link
        google_drive_link = (
            f'<p><b>Project Pictures:</b> <a href="https://drive.google.com/drive/folders/{project.google_folder_id}" target="_blank">View Files</a></p>'
            if project.google_folder_id and folder_has_files(project.google_folder_id) else ""
        )

        subject = f"Project Completion Notification: {project.client_name} installation has been Completed"

        body = f"""
        <p>Dear {project.sales_person},</p>
        <p>Your installation for <b>{project.client_name}</b> in <b>{project.town}</b> has now been marked as <b>Completed</b>.</p>
        <p><b>Project Details:</b></p>
        <ul>
            <li>Client Name: {project.client_name}</li>
            <li>Town: {project.town}</li>
            <li>Start Date: {format_date_with_suffix(project.start_date)}</li>
            <li>Commissioning Date: {format_date_with_suffix(project.commissioning_date)}</li>
            <li>Lead Installer: {project.lead_installer}</li>
        </ul>
        {google_maps_link}
        {invoice_link}
        {google_drive_link}
        <p>You can check the status of other projects by clicking <a href="https://tino-solutions-reports-49ba7768c4e2.herokuapp.com/projects" target="_blank">here</a>.</p>
        <p>Thank you for your efforts in ensuring the successful completion of this project.</p>
        <p>Kind regards,<br>Emmanuel Kwesi Padi</p>
        """
        #<hr>
        #<p style="font-size: 12px; color: gray;">This email was automatically generated from the Tino Solutions System Database.</p>

        msg = Message(
            subject,
            #recipients=["emmanuel@tinosolutions.com"],
            recipients=[sales_person_email],
            #cc=["emmanuel@tinosolutions.com"],
            cc=["hippolite@tinosolutions.com", "support@tinosolutions.com"],
            bcc=["augustine@tinosolutions.com", "emmanuel@tinosolutions.com"],  # Add BCC recipients
            html=body
        )

        try:
            mail.send(msg)
            print(f"Email sent to {sales_person_email} for completed project {project.client_name}")
        except Exception as e:
            print(f"ERROR: Failed to send email to {sales_person_email}: {e}")


@app.route("/upload_invoice", methods=["POST"])
def upload_invoice():
    project_id = request.form.get("project_id")  # Get project_id from form data

    if not project_id:
        return jsonify({"message": "Project ID is required. Please enter the other parameters on the row"}), 400

    if "invoice_image" not in request.files:
        return jsonify({"message": "No file uploaded"}), 400

    file = request.files["invoice_image"]
    if file.filename == "":
        return jsonify({"message": "No selected file"}), 400

    # Save file temporarily
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    try:
        # Upload to Google Drive using the root folder ID
        file_url = upload_to_drive(file_path, file.filename, GOOGLE_DRIVE_FOLDER_ID)

        # Remove the temporary file
        os.remove(file_path)

        # Update the project in the database with the invoice URL
        project = db.session.query(projects).filter_by(project_id=project_id).first()
        if project:
            project.invoice_image_url = file_url
            db.session.commit()

            # Return a success message to the frontend
            return jsonify({"message": "Upload successful", "file_url": file_url, "refresh": True})

        else:
            return jsonify({"message": "Project not found"}), 404

    except Exception as e:
        logging.error(f"Error uploading file: {e}")
        return jsonify({"message": "Error uploading file"}), 500

import os
import json
import base64
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Load credentials from Heroku environment variable
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

if GOOGLE_CREDENTIALS:
    credentials_json = json.loads(base64.b64decode(GOOGLE_CREDENTIALS).decode("utf-8"))
    credentials = service_account.Credentials.from_service_account_info(credentials_json)
else:
    raise ValueError("GOOGLE_CREDENTIALS environment variable not set.")

# Authenticate and build the Google Drive service
SCOPES = ["https://www.googleapis.com/auth/drive"]
credentials = credentials.with_scopes(SCOPES)
service = build("drive", "v3", credentials=credentials)

# Folder ID to check
FOLDER_ID = "15ANbwh6M8c7eAp_o8vWToOHs-ObjdLP9"

# Function to list files in the folder
def list_files_in_folder(service, folder_id):
    query = f"'{folder_id}' in parents"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if not files:
        print("No files found or no access to folder.")
    else:
        print("Files in folder:")
        for file in files:
            print(f"{file['name']} ({file['id']})")

# Call the function to list files
# list_files_in_folder(service, FOLDER_ID)

def get_or_create_folder(service, parent_folder_id, project_id, client_name, town, sales_person):
    """Ensure a single folder per project_id and rename it if necessary."""
    # Query MySQL for existing folder ID
    project = db.session.query(projects).filter_by(project_id=project_id).first()
    existing_folder_id = project.google_folder_id if project else None

    # Define expected folder name
    expected_folder_name = f"{client_name}_{town}_{sales_person}_{project_id}"

    if existing_folder_id:
        try:
            # Get current folder name from Google Drive
            folder_metadata = service.files().get(fileId=existing_folder_id, fields="name").execute()
            current_folder_name = folder_metadata.get("name", "")

            if current_folder_name != expected_folder_name:
                # Rename folder if the name has changed
                service.files().update(fileId=existing_folder_id, body={"name": expected_folder_name}).execute()

            return existing_folder_id  # Return the existing folder ID
        except Exception as e:
            logging.error(f"Error fetching folder {existing_folder_id}: {e}")

    # If no existing folder ID, search for the folder in Drive
    query = f"mimeType='application/vnd.google-apps.folder' and trashed=false and name contains '{project_id}' and '{parent_folder_id}' in parents"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = results.get("files", [])

    if folders:
        folder_id = folders[0]["id"]
        if folders[0]["name"] != expected_folder_name:
            # Rename if the folder exists but has a different name
            service.files().update(fileId=folder_id, body={"name": expected_folder_name}).execute()

        # Update the database with the correct folder ID
        if project:
            project.google_folder_id = folder_id
            db.session.commit()

        return folder_id

    # If no folder exists, create a new one
    file_metadata = {
        "name": expected_folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }
    folder = service.files().create(body=file_metadata, fields="id").execute()
    folder_id = folder["id"]

    # Save new folder ID in the database
    if project:
        project.google_folder_id = folder_id
        db.session.commit()

    return folder_id




@app.route("/upload_file_to_folder", methods=["POST"])
def upload_file_to_folder():
    folder_id = request.form.get("folder_id")

    if not folder_id:
        return jsonify({"message": "Folder ID is required"}), 400

    if "file" not in request.files:
        return jsonify({"message": "No file uploaded"}), 400

    files = request.files.getlist("file")  # Get multiple files

    if not files or all(f.filename == "" for f in files):
        return jsonify({"message": "No selected files"}), 400

    uploaded_files = []  # Store uploaded file URLs

    for file in files:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)

        try:
            file_url = upload_to_drive(file_path, file.filename, folder_id)
            os.remove(file_path)  # Delete temporary file
            uploaded_files.append(file_url)  # Store file URL

        except Exception as e:
            logging.error(f"Error uploading file {file.filename}: {e}")
            return jsonify({"message": f"Error uploading file {file.filename}: {str(e)}"}), 500

    # Redirect to projects.html after successful upload
    return redirect(url_for("get_projects"))

    #return jsonify({"message": "Upload successful", "files": uploaded_files})

def folder_has_files(folder_id):
    """Check if the given Google Drive folder contains any files."""
    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id)",
            pageSize=1  # We only need to check if at least one file exists
        ).execute()
        return bool(results.get('files', []))  # Returns True if files exist, False otherwise
    except Exception as e:
        print(f"Error checking folder contents: {e}")
        return False


from datetime import datetime, timedelta

@app.route('/bdu', methods=['GET'])
def get_bdu():
    message = request.args.get('message', '')
    start_date_from = request.args.get('start_date_from')
    start_date_to = request.args.get('start_date_to')
    search_query = request.args.get('search_query', '').strip().lower()


    try:
        # Convert date inputs to proper format
        start_date = datetime.strptime(start_date_from, '%Y-%m-%d').date() if start_date_from else None
        end_date = datetime.strptime(start_date_to, '%Y-%m-%d').date() if start_date_to else None

        # Base query for projects
        query = db.session.query(
            projects.project_id,
            projects.invoice_image_url,
            projects.client_name,
            projects.town,
            projects.phone_number,
            projects.sales_person,
            projects.google_coordinates,
            projects.currency,
            projects.invoice_amount,
            projects.amount_paid,
            projects.expected_final_payment_date,
            projects.commissioning_date,
            projects.comment
        )

        # Apply date filtering based on start_date
        if start_date and end_date:
            query = query.filter(
                projects.start_date >= start_date,
                projects.start_date <= end_date
            )
        elif start_date:
            query = query.filter(projects.start_date >= start_date)
        elif end_date:
            query = query.filter(projects.start_date <= end_date)

        # Apply search filter if a query is provided
        if search_query:
            query = query.filter(
                (projects.client_name.ilike(f"%{search_query}%")) |
                (projects.town.ilike(f"%{search_query}%")) |
                (projects.phone_number.ilike(f"%{search_query}%")) |
                (projects.sales_person.ilike(f"%{search_query}%")) |
                (projects.lead_installer.ilike(f"%{search_query}%")) |
                (projects.currency.ilike(f"%{search_query}%")) |
                (projects.comment.ilike(f"%{search_query}%"))
            )

        # Fetch filtered projects
        projects_list = query.all()

        team_members = db.session.query(Team_Members.Team_Member_Name).all()
        team_members = [member.Team_Member_Name for member in team_members]

        closed_deals = []
        clients_in_debt = []
        clients_in_good_standing = []

        today = datetime.today().date()

        for project in projects_list:
            invoice_amount = Decimal(project.invoice_amount or 0.00)
            amount_paid = Decimal(project.amount_paid or 0.00)
            outstanding_balance = invoice_amount - amount_paid  # Dynamically calculate Outstanding Balance

            # Handle commissioning_date format
            if isinstance(project.commissioning_date, str):
                if project.commissioning_date == '0000-00-00':
                    commissioning_date = None  # Treat as missing date
                else:
                    commissioning_date = datetime.strptime(project.commissioning_date, '%Y-%m-%d').date()
            else:
                commissioning_date = project.commissioning_date  # Already a datetime.date

            expected_payment_date = project.expected_final_payment_date.strftime('%Y-%m-%d') if project.expected_final_payment_date else ''

            project_data = {
                "project_id": project.project_id,
                "invoice_image_url": project.invoice_image_url or '',
                "client_name": project.client_name or '',
                "town": project.town or '',
                "phone_number": project.phone_number or '',
                "sales_person": project.sales_person or '',
                "google_coordinates": project.google_coordinates or '',
                "currency": project.currency or '',
                "invoice_amount": invoice_amount,
                "amount_paid": amount_paid,
                "outstanding_balance": outstanding_balance,
                "expected_final_payment_date": expected_payment_date,
                "comment": project.comment or ''
            }

            # Categorization logic
            if commissioning_date is None or commissioning_date > today:
                closed_deals.append(project_data)
            elif commissioning_date <= today and outstanding_balance > 0:
                clients_in_debt.append(project_data)
            elif commissioning_date <= today and outstanding_balance <= 0:
                clients_in_good_standing.append(project_data)

        return render_template(
            'bdu.html',
            closed_deals=closed_deals,
            clients_in_debt=clients_in_debt,
            clients_in_good_standing=clients_in_good_standing,
            team_members=team_members,
            message=message,
            search_query=search_query,  # Ensure search query is passed back
            start_date_from=start_date_from,
            start_date_to=start_date_to
        )

    except Exception as e:
        logging.error(f"Error fetching BDU data: {e}")
        return render_template('bdu.html', message='Database query failed', closed_deals=[], clients_in_debt=[], clients_in_good_standing=[], team_members=[])


@app.route('/update_bdu', methods=['POST'])
def update_bdu():
    try:
        data = request.json.get('records', [])

        for record in data:
            project_id = record.get('project_id')

            if project_id:
                existing_project = db.session.query(projects).filter_by(project_id=project_id).first()

                if existing_project:
                    # Only update fields that have changed
                    for field in ['client_name', 'town', 'phone_number', 'google_coordinates',
                                  'currency', 'invoice_amount', 'outstanding_balance',
                                  'comment', 'invoice_image_url']:
                        if field in record and record[field] != getattr(existing_project, field):
                            setattr(existing_project, field, record[field])

                    # Handle `amount_paid` carefully to avoid setting it to 0
                    if 'amount_paid' in record:
                        if record['amount_paid'] is not None:
                            existing_project.amount_paid = record['amount_paid']

                    # Handle `sales_person` safely
                    if 'sales_person' in record:
                        new_sales_person = record['sales_person'].strip()
                        if new_sales_person:  # Prevent overwriting with an empty value
                            existing_project.sales_person = new_sales_person

                    # Handle `lead_installer` safely
                    if 'lead_installer' in record:
                        new_lead_installer = record['lead_installer'].strip()
                        if new_lead_installer:  # Prevent overwriting with an empty value
                            existing_project.lead_installer = new_lead_installer

                    # Handle `expected_final_payment_date`
                    expected_payment_date = record.get('expected_final_payment_date', '').strip()
                    existing_project.expected_final_payment_date = expected_payment_date if expected_payment_date else None

        db.session.commit()
        return jsonify({"message": "BDU records updated successfully"})

    except Exception as e:
        logging.error(f"Error updating BDU records: {e}")
        return jsonify({"message": "Error updating BDU records"}), 500


import requests
import json
import logging
from flask import render_template
from datetime import datetime

def safe_date_format(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value  # already a string
    return value.strftime('%Y-%m-%d')  # datetime object

import requests

@app.route('/reports', methods=['GET'])
def reports():
    try:
        # Fetch exchange rate from exchangerate-api.com
        exchange_api_url = 'https://api.exchangerate-api.com/v4/latest/USD'
        response = requests.get(exchange_api_url)
        if response.status_code != 200:
            raise Exception("Failed to fetch exchange rate data from exchangerate-api.")

        exchange_data = response.json()
        usd_to_ghs = exchange_data['rates'].get('GHS')

        if not usd_to_ghs:
            raise Exception("USD to GHS exchange rate not found.")

        projects_list = db.session.query(projects).all()
        data = []
        for p in projects_list:
            rate = usd_to_ghs if p.currency == 'GHC' else 1
            invoice_amount_usd = float(p.invoice_amount or 0) / rate
            amount_paid_usd = float(p.amount_paid or 0) / rate
            outstanding_balance_usd = invoice_amount_usd - amount_paid_usd

            data.append({
                "start_date": safe_date_format(p.start_date),
                "commissioning_date": safe_date_format(p.commissioning_date),
                "sales_person": p.sales_person,
                "town": p.town,
                "invoice_amount": round(invoice_amount_usd, 2),
                "amount_paid": round(amount_paid_usd, 2),
                "expected_final_payment_date": safe_date_format(p.expected_final_payment_date),
                "outstanding_balance": round(outstanding_balance_usd, 2)
            })

        return render_template("reports.html", project_data=json.dumps(data))

    except Exception as e:
        logging.error(f"Error generating reports: {e}")
        return render_template("reports.html", project_data="[]", error="Could not load data.")



if __name__ == '__main__':

    # Ensure the upload folder exists
    #if not os.path.exists(UPLOAD_FOLDER):
    #    os.makedirs(UPLOAD_FOLDER)

    # Use the port from environment variables; default to 5000 for local development
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)


#    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))  # Use environment variable for port
