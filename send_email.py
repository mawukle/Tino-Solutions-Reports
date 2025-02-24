from bs4 import BeautifulSoup
import datetime
import pytz
from flask_mail import Message
from app import app, mail  # Import Flask app and Mail instance
from flask import render_template

# Define scheduled email times (UTC)
SCHEDULED_TIMES = {
    "2025-02-24": "18:00",
    "2025-02-24": "18:10",
    "2025-03-29": "08:00",
    "2025-04-30": "08:00",
}

def is_scheduled_time():
    """Check if the current UTC time is within a 10-minute window of a scheduled time."""
    utc_now = datetime.datetime.now(pytz.utc)
    current_date = utc_now.strftime("%Y-%m-%d")

    if current_date in SCHEDULED_TIMES:
        scheduled_time = datetime.datetime.strptime(SCHEDULED_TIMES[current_date], "%H:%M").time()
        scheduled_datetime = datetime.datetime.combine(utc_now.date(), scheduled_time).replace(tzinfo=pytz.utc)

        time_difference = abs((utc_now - scheduled_datetime).total_seconds())

        return time_difference <= 600  # 600 seconds = 10 minutes
    return False

def fetch_client_list_html():
    """Retrieve the rendered HTML content from the /client_list route with the email_mode filter applied."""
    with app.test_client() as client:
        response = client.get('/client_list?email_mode=1')  # Use the email mode filter
        if response.status_code == 200:
            full_html = response.get_data(as_text=True)

            # Parse HTML and extract only the Tino Team table
            soup = BeautifulSoup(full_html, 'html.parser')
            tino_team_table = soup.find(id="tino_team_table")

            if tino_team_table:
                return str(tino_team_table)
            else:
                print("ERROR: 'tino_team_table' div not found in HTML.")
                return None
        else:
            print(f"ERROR: Failed to fetch client list (HTTP {response.status_code})")
            return None

def send_client_list_email():
    """Send an email with only the 'Installed by Tino Team' table and an introductory message."""
    if not is_scheduled_time():
        print(f"Not the scheduled time ({datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}). Exiting.")
        return

    recipient = "padiemmanuelkwesi@yahoo.com"  # Main recipient
    cc_recipients = ["padiemmanuelkwesi@gmail.com"]  # CC recipient

    with app.app_context():  # Ensure Flask context is available
        subject = "Client List Report"
        body_content = fetch_client_list_html()

        if body_content:
            # Email content with introductory message
            styled_body = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; padding: 20px; background-color: #f9f9f9;">
                <p>Dear Team,</p>
                <p>
                    Please find below details of installed systems for the past 7 months.
                    Kindly click on any of the client names in
                    <a href="https://tino-solutions-reports-49ba7768c4e2.herokuapp.com/client_list?email_mode=1"
                    style="color: #004085; text-decoration: none; font-weight: bold;">
                        our client list
                    </a>
                    if you need further details about a given client.
                </p>
                <p>Kind regards,<br>Emmanuel Kwesi Padi</p>

                <h2 style="color: #004085; text-align: center;">Client List Report</h2>
                <div style="border: 1px solid #ddd; padding: 15px; background-color: #fff;">
                    {body_content}
                </div>
                <p style="text-align: center; margin-top: 20px; font-size: 12px; color: #666;">
                    This is an automated email from the Tino Solutions System Database.
                </p>
            </div>
            """

            # Create the email message
            msg = Message(subject, recipients=[recipient], cc=cc_recipients, html=styled_body)

            try:
                mail.send(msg)
                print("Email sent successfully!")
            except Exception as e:
                print(f"ERROR: Failed to send email: {e}")
        else:
            print("ERROR: Client list HTML is empty. Email not sent.")

if __name__ == "__main__":
    send_client_list_email()
