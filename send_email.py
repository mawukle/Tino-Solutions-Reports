import os
import datetime
import pytz
from flask_mail import Message
from app import app, mail  # Import Flask app and Mail instance
from flask import render_template

# Define scheduled email times (UTC)
SCHEDULED_TIMES = {
    "2025-02-23": "20:50",
    "2025-02-23": "21:00",
    "2025-03-29": "08:00",
    "2025-04-30": "08:00",
}

def is_scheduled_time():
    """Check if the current UTC time is within a 10-minute window of a scheduled time."""
    utc_now = datetime.datetime.now(pytz.utc)
    current_date = utc_now.strftime("%Y-%m-%d")

    print(f"DEBUG: Current UTC Date-Time: {utc_now}")

    if current_date in SCHEDULED_TIMES:
        scheduled_time = datetime.datetime.strptime(SCHEDULED_TIMES[current_date], "%H:%M").time()
        scheduled_datetime = datetime.datetime.combine(utc_now.date(), scheduled_time).replace(tzinfo=pytz.utc)

        time_difference = abs((utc_now - scheduled_datetime).total_seconds())

        print(f"DEBUG: Scheduled Date-Time: {scheduled_datetime}")
        print(f"DEBUG: Time Difference (seconds): {time_difference}")

        return time_difference <= 600  # 600 seconds = 10 minutes

    print("DEBUG: No matching schedule found for today.")
    return False


def send_client_list_email():
    """Send an email with the client list if the current time matches a scheduled date and time."""
    if not is_scheduled_time():
        print(f"Not the scheduled time ({datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}). Exiting.")
        return

    recipients = ["padiemmanuelkwesi@yahoo.com", "padiemmanuelkwesi@gmail.com"]  # Replace with actual emails

    with app.app_context():  # Ensure Flask context is available
        subject = "Client List Report"

        # Manually construct the absolute URL for the stylesheet instead of using url_for
        body = render_template("client_list.html", static_url="/static/style.css")

        msg = Message(subject, recipients=recipients, html=body)

        try:
            mail.send(msg)
            print("Email sent successfully!")
        except Exception as e:
            print(f"Error sending email: {e}")

if __name__ == "__main__":
    send_client_list_email()
