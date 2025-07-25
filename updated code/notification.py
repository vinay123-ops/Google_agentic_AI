from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from firebase_admin import messaging, initialize_app, credentials
import logging
import os
import asyncio

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI
app = FastAPI(title="Notification Agent")

# Initialize Firebase for FCM
cred = credentials.Certificate("serviceAccountKey.json")
initialize_app(cred)

# Email configs
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "your_email@gmail.com")
SENDER_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "your_email_password")
DEFAULT_RECIPIENTS = os.getenv("DEFAULT_RECIPIENTS", "user1@example.com,user2@example.com").split(",")

# Pydantic model
class NotificationPayload(BaseModel):
    subject: str
    message: str
    location: str
    recipients: List[str] = DEFAULT_RECIPIENTS

# Send email
async def send_email_alert(subject: str, message: str, location: str, recipients: List[str]):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    full_message = f"📍 **Location**: {location}\n\n{message}"
    msg.attach(MIMEText(full_message, "plain"))
    
    async with aiosmtplib.SMTP(hostname=SMTP_SERVER, port=SMTP_PORT, use_tls=True) as server:
        await server.login(SENDER_EMAIL, SENDER_PASSWORD)
        await server.send_message(msg)

# Send FCM push notification
async def send_fcm_alert(subject: str, message: str, location: str):
    msg = messaging.Message(
        notification=messaging.Notification(
            title=subject,
            body=f"Location: {location}\n{message}"
        ),
        topic="security_alerts"  # TODO: Configure FCM topic or device tokens
    )
    messaging.send(msg)

# Notify endpoint
@app.post("/notify")
async def notify(payload: NotificationPayload):
    try:
        # Send both email and FCM notifications
        await asyncio.gather(
            send_email_alert(payload.subject, payload.message, payload.location, payload.recipients),
            send_fcm_alert(payload.subject, payload.message, payload.location)
        )
        logging.info(f"Notifications sent for location: {payload.location}")
        return {"status": "success", "message": "Email and FCM notifications sent"}
    except Exception as e:
        logging.error(f"Error sending notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "notification agent alive"}