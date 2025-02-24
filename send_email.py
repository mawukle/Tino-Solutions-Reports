import os
import datetime
import pytz
from flask_mail import Message
from app import app, mail  # Import Flask app and Mail instance
from flask import render_template

# Define scheduled email times (UTC)
SCHEDULED_TIMES = {
    "2025-02-24": "10:40",
    "2025-02-24": "10:50",
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

def fetch_client_list_html():
    """Retrieve the rendered HTML content from the /client_list route."""
    with app.test_client() as client:
        response = client.get('/client_list')
        if response.status_code == 200:
            return response.get_data(as_text=True)
        else:
            print(f"ERROR: Failed to fetch client list (HTTP {response.status_code})")
            return None

def send_client_list_email():
    """Send an email with the client list if the current time matches a scheduled date and time."""
    if not is_scheduled_time():
        print(f"Not the scheduled time ({datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}). Exiting.")
        return

    recipients = ["padiemmanuelkwesi@yahoo.com", "padiemmanuelkwesi@gmail.com"]

    with app.app_context():  # Ensure Flask context is available
        subject = "Client List Report"
        body_content = fetch_client_list_html()

        if body_content:
            # Apply inline styles
            styled_body = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; padding: 20px; background-color: #f9f9f9;">
                <h2 style="color: #004085; text-align: center;">Client List Report</h2>
                <div style="border: 1px solid #ddd; padding: 15px; background-color: #fff;">
                    {body_content}
                </div>
                <p style="text-align: center; margin-top: 20px; font-size: 12px; color: #666;">
                    This is an automated email from the Tino Solutions system.
                </p>
            </div>
            """

            msg = Message(subject, recipients=recipients, html=styled_body)
            try:
                mail.send(msg)
                print("Email sent successfully!")
            except Exception as e:
                print(f"ERROR: Failed to send email: {e}")
        else:
            print("ERROR: Client list HTML is empty. Email not sent.")

if __name__ == "__main__":
    send_client_list_email()
