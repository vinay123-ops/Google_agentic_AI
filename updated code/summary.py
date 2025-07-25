from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import pubsub_v1
from firebase_admin import db, initialize_app, credentials
import json
import logging
import uuid
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI
app = FastAPI(title="Summary Agent")

# Google Cloud configs
PROJECT_ID = "your-gcp-project-id"
SUMMARY_TOPIC = "summary-events"

# Initialize Google Cloud clients
subscriber = pubsub_v1.SubscriberClient()

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
initialize_app(cred, {'databaseURL': 'https://your-project.firebaseio.com'})
db_ref = db.reference("/summaries")

# Pydantic model
class EventLog(BaseModel):
    eventId: str
    type: str
    severity: str
    location: str
    timestamp: str
    details: str = ""

# Placeholder for Gemini
def summary_generator(event: dict) -> str:
    # TODO: Integrate Google Gemini for NLP-based summarization
    # Input: Event data; Output: Human-readable summary
    return f"{event.get('severity', 'Unknown').title()} {event.get('message', 'event')} at {event.get('location', 'Unknown')} on {event.get('timestamp', 'Unknown')}."

# Process event from Pub/Sub
def callback(message):
    event = json.loads(message.data.decode('utf-8'))
    event_id = str(uuid.uuid4())
    
    # Generate summary
    summary_text = summary_generator(event)
    summary_data = {
        "summary": summary_text,
        "eventIds": [event.get("camera_id", "unknown")],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "language": "en",
        "source": "summary-agent"
    }
    
    # Store in Firebase
    db_ref.child(event_id).set(summary_data)
    
    message.ack()

# Start Pub/Sub subscription
@app.on_event("startup")
async def start_subscription():
    subscription_path = subscriber.subscription_path(PROJECT_ID, "summary-sub")
    subscriber.subscribe(subscription_path, callback=callback)
    logging.info("Summary Agent subscribed to Pub/Sub")

@app.get("/summaries")
async def get_all_summaries():
    summaries = db_ref.get() or {}
    return [{"id": key, **value} for key, value in summaries.items()]

@app.get("/health")
async def health():
    return {"status": "summary agent alive"}