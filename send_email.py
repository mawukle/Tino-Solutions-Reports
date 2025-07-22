import datetime
import pytz
from flask_mail import Message
from app import app, mail, db
from flask import render_template
from bs4 import BeautifulSoup
from models import projects, Team_Members  # Ensure correct import paths

# Define scheduled email times (UTC) for client list
SCHEDULED_TIMES = {
    "2025-02-28": "08:00",
    "2025-02-28": "08:10",
    "2025-03-31": "08:00",
    "2025-03-31": "08:10",
    "2025-04-30": "08:00",
    "2025-04-30": "08:10",
}

# Define scheduled email times (UTC) for payment reminders
PAYMENT_REMINDER_TIMES = ["09:00", "09:10"]  # UTC

def is_scheduled_time(schedule_times):
    """Check if the current UTC time is within a 10-minute window of a scheduled time."""
    utc_now = datetime.datetime.now(pytz.utc)
    current_time = utc_now.strftime("%H:%M")

    for scheduled_time in schedule_times:
        scheduled_datetime = datetime.datetime.combine(utc_now.date(), datetime.datetime.strptime(scheduled_time, "%H:%M").time()).replace(tzinfo=pytz.utc)
        time_difference = abs((utc_now - scheduled_datetime).total_seconds())

        if time_difference <= 600:  # 600 seconds = 10 minutes
            return True
    return False

def send_client_list_email():
    """Send the client list email at scheduled times."""
    if not is_scheduled_time(SCHEDULED_TIMES.values()):
        return

    with app.app_context():
        recipient = ["emmanuel@tinosolutions.com"]
        #recipient = ["hippolite@tinosolutions.com", "support@tinosolutions.com", "service@tinosolutions.com"]
        #cc_recipients = ["gorden@tinosolutions.com", "augustine@tinosolutions.com", "philip@tinosolutions.com",
                         #"solal@tinosolutions.com", "kwame@tinosolutions.com", "naalenuo@tinosolutions.com",
                         #"patrick@tinosolutions.com", "reports@tinosolutions.com", "marketing@tinosolutions.com", "sales@tinosolutions.com"]

        response = app.test_client().get('/client_list?email_mode=1')
        if response.status_code != 200:
            print(f"ERROR: Failed to fetch client list (HTTP {response.status_code})")
            return

        soup = BeautifulSoup(response.get_data(as_text=True), 'html.parser')
        tino_team_table = soup.find(id="tino_team_table")

        if not tino_team_table:
            print("ERROR: 'tino_team_table' div not found in HTML.")
            return

        styled_body = f"""
        <p>Dear Team,</p>
        <p>Please find below details of installed systems within the past 12 months.</p>
        <p>Click <a href="https://tino-solutions-reports-49ba7768c4e2.herokuapp.com/client_list">here</a> for more details.</p>
        <h2 style="color: #004085;">Client List Report</h2>
        {str(tino_team_table)}
        <p>This is an automated email from the Tino Solutions System.</p>
        """

        #msg = Message("Client List Report", recipients=recipient, cc=cc_recipients, html=styled_body)
        msg = Message("Client List Report", recipients=recipient, html=styled_body)
        try:
            mail.send(msg)
            print("Client list email sent successfully!")
        except Exception as e:
            print(f"ERROR: Failed to send client list email: {e}")

def send_payment_reminders():
    """Send payment reminders at scheduled times (9:00 and 9:10 GMT daily)."""
    if not is_scheduled_time(PAYMENT_REMINDER_TIMES):
        return

    with app.app_context():
        today = datetime.datetime.now(pytz.utc).date()
        projects_list = db.session.query(
            projects.client_name, projects.sales_person, projects.invoice_amount,
            projects.amount_paid, projects.expected_final_payment_date,
            projects.commissioning_date, projects.google_coordinates,
            projects.invoice_image_url, projects.currency  # ✅ Added currency
        ).all()

        for project in projects_list:
            invoice_amount = project.invoice_amount or 0
            amount_paid = project.amount_paid or 0
            outstanding_balance = invoice_amount - amount_paid
            currency = project.currency or ''  # ✅ Default to empty string if null

            if outstanding_balance <= 0:
                continue  # Skip if fully paid

            sales_person_email = db.session.query(Team_Members.Team_Member_Email).filter(
                Team_Members.Team_Member_Name == project.sales_person
            ).scalar()
            if not sales_person_email:
                continue  # Skip if email not found

            should_send_email = False

            if project.expected_final_payment_date:
                due_date = project.expected_final_payment_date
                if due_date == today or (today > due_date and (today - due_date).days % 14 == 0):
                    should_send_email = True

            elif project.commissioning_date:
                commissioning_date = project.commissioning_date  # Ensure it's already a date object
                if isinstance(commissioning_date, str):
                    if commissioning_date in ["0000-00-00", None, ""]:  # Check for invalid or empty values
                        continue  # Skip this record to prevent errors
                    try:
                        commissioning_date = datetime.datetime.strptime(commissioning_date, "%Y-%m-%d").date()
                    except ValueError as e:
                        print(f"Skipping invalid commissioning date: {commissioning_date} - {e}")
                        continue  # Skip the record if the date is invalid
                due_date = commissioning_date + datetime.timedelta(days=14)
                if due_date == today or (today > due_date and (today - due_date).days % 14 == 0):
                    should_send_email = True

            if should_send_email:
                email_body = f"""
                <p>Dear {project.sales_person},</p>
                <p>This is a reminder for the payment of <b>{project.client_name}</b>.</p>
                <p><b>Invoice Amount:</b> {currency} {invoice_amount:,.2f}</p>
                <p><b>Amount Paid:</b> {currency} {amount_paid:,.2f}</p>
                <p><b>Outstanding Balance:</b> {currency} {outstanding_balance:,.2f}</p>
                """
                if project.google_coordinates:
                    email_body += f'<p><b>Location:</b> <a href="https://www.google.com/maps?q={project.google_coordinates}" target="_blank">View on Google Maps</a></p>'
                if project.invoice_image_url:
                    email_body += f'<p><b>Invoice:</b> <a href="{project.invoice_image_url}" target="_blank">View Invoice</a></p>'

                from urllib.parse import urlencode

                search_url = f"https://tino-solutions-reports-49ba7768c4e2.herokuapp.com/bdu?{urlencode({'search_query': project.sales_person})}"

                email_body += f"""
                <p><b>Update Payment Details:</b></p>
                <p>If the provided data is not a true reflection of the client’s debt status,
                you can update it by clicking <a href="{search_url}" target="_blank">this link</a>,
                editing the <b>Amount Paid</b> column, and then clicking <b>Save Changes</b> at the bottom of the page.</p>
                """

                email_body += """
                <p><b>Modify Expected Payment Date:</b></p>
                <p>If you would like to postpone future reminders, you can change the <b>Expected Final Payment Date</b>
                to a later date on the same page.</p>
                """

                email_body += "<p>Kind regards,<br>Augustine Beyuo</p>"

                msg = Message(
                    subject=f"Payment Reminder: {project.client_name}",
                    recipients=[sales_person_email],
                    #recipients=["emmanuel@tinosolutions.com"],
                    cc=["finance@tinosolutions.com", "accounts@tinosolutions.com"],
                    #cc=["padiemmanuelkwesi@gmail.com", "padiemmanuelkwesi@yahoo.com"],
                    bcc=["emmanuel@tinosolutions.com","augustine@tinosolutions.com"],
                    html=email_body
                )

                try:
                    mail.send(msg)
                    print(f"Payment reminder sent to {sales_person_email} for {project.client_name}")
                except Exception as e:
                    print(f"ERROR: Failed to send payment reminder to {sales_person_email}: {e}")

if __name__ == "__main__":
    send_client_list_email()
    send_payment_reminders()
