import os
import datetime
import pytz
from flask_mail import Message
from app import app, mail  # Import Flask app and Mail instance
from flask import render_template

# Define scheduled email times (UTC)
SCHEDULED_TIMES = {
    "2025-02-23": "18:00",
    "2025-02-23": "19:00",
    "2025-03-29": "08:00",
    "2025-04-30": "08:00",
}

def is_scheduled_time():
    """Check if the current UTC time matches a scheduled date and time."""
    utc_now = datetime.datetime.now(pytz.utc)
    current_date = utc_now.strftime("%Y-%m-%d")
    current_time = utc_now.strftime("%H:%M")

    return current_date in SCHEDULED_TIMES and current_time == SCHEDULED_TIMES[current_date]

def send_client_list_email():
    """Send an email with the client list if the current time matches a scheduled date and time."""
    if not is_scheduled_time():
        print(f"Not the scheduled time ({datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}). Exiting.")
        return

    recipients = ["padiemmanuelkwesi@yahoo.com", "padiemmanuelkwesi@gmail.com"]  # Replace with actual emails

    with app.app_context():  # Ensure Flask context is available
        subject = "Client List Report"
        body = render_template("client_list.html")  # Render the HTML page for email content

        msg = Message(subject, recipients=recipients, html=body)

        try:
            mail.send(msg)
            print("Email sent successfully!")
        except Exception as e:
            print(f"Error sending email: {e}")

if __name__ == "__main__":
    send_client_list_email()
