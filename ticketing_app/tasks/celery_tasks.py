from celery import Celery
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

# Initialize Celery
celery_app = Celery(
    "support_tickets",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


@celery_app.task
def send_reply_notification(user_email: str, ticket_title: str, reply_message: str):
    """Send email notification when agent replies to ticket"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = user_email
        msg['Subject'] = f"New Reply to Your Ticket: {ticket_title}"

        body = f"""
        Dear Customer,

        You have received a new reply to your support ticket: "{ticket_title}"

        Reply:
        {reply_message}

        Please log in to your account to view the full conversation.

        Best regards,
        Support Team
        """

        msg.attach(MIMEText(body, 'plain'))

        # Send email (only if SMTP is configured)
        if SMTP_USERNAME and SMTP_PASSWORD:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            text = msg.as_string()
            server.sendmail(SMTP_USERNAME, user_email, text)
            server.quit()

            print(f"Email sent to {user_email}")
        else:
            print(f"Would send email to {user_email}: {ticket_title}")

    except Exception as e:
        print(f"Failed to send email: {e}")


@celery_app.task
def log_reply_event(ticket_id: int, agent_id: int, message: str):
    """Log reply events to file."""
    try:
        timestamp = datetime.now().isoformat()
        truncated_msg = message[:50]
        log_entry = (
            f"{timestamp} - Ticket {ticket_id} - "
            f"Agent {agent_id} replied: {truncated_msg}...\n"
        )

        os.makedirs("logs", exist_ok=True)
        with open("logs/replies.log", "a", encoding="utf-8") as log_file:
            log_file.write(log_entry)

        print(f"Logged reply event for ticket {ticket_id}")

    except Exception as e:
        print(f"Failed to log reply event: {e}")
