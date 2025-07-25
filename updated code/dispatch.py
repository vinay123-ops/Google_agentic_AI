from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import logging
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db, messaging
from google.cloud import pubsub_v1

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize Firebase
cred = credentials.Certificate("drishti-firebase-adminsdk.json")  # Update with your Firebase key
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://drishti.firebaseio.com/'  # Update with your Firebase URL
})
db_ref = db.reference()

# Initialize Pub/Sub subscriber
project_id = "your-gcp-project-id"  # Update with your GCP project ID
subscription_name = "dispatch-events-sub"
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_name)

app = FastAPI(title="Drishti Dispatch Agent")

# Data models (reused from provided code)
class CriticalEvent(BaseModel):
    eventId: str
    type: str  # e.g., fire, medical
    severity: str  # e.g., high
    location: str
    timestamp: str

class FieldUnit(BaseModel):
    unitId: str
    type: str
    status: str
    location: str
    fcm_token: str | None = None

class DispatchInstruction(BaseModel):
    eventId: str
    action: str
    units: List[FieldUnit]
    timestamp: str
    eta: float | None = None

# Simplified action mapper
def action_mapper(event: CriticalEvent) -> str:
    action_map = {
        "fire": {"high": "Deploy firefighter"},
        "medical": {"high": "Deploy medic"},
    }
    return action_map.get(event.type, {}).get(event.severity, "Notify supervisor")

# Simplified unit locator
def unit_locator(event: CriticalEvent, action: str) -> List[FieldUnit]:
    units_data = db_ref.child("field_units").get() or {}
    available_units = [
        FieldUnit(**unit_data, unitId=unit_id)
        for unit_id, unit_data in units_data.items()
        if unit_data.get("status") == "available"
    ]
    required_type = "firefighter" if "firefighter" in action else "medic"
    units = [unit for unit in available_units if unit.type == required_type][:1]
    if not units:
        logger.warning(f"No available units for event: {event.eventId}")
        raise HTTPException(status_code=503, detail="No available units")
    for unit in units:
        db_ref.child(f"field_units/{unit.unitId}").update({"status": "busy"})
    return units

# Dispatch sender
def dispatch_sender(event: CriticalEvent, action: str, units: List[FieldUnit]) -> DispatchInstruction:
    instruction = DispatchInstruction(
        eventId=event.eventId,
        action=action,
        units=units,
        timestamp=datetime.utcnow().isoformat(),
        eta=5.0  # Mock ETA for demo
    )
    db_ref.child(f"dispatch_instructions/{event.eventId}").set(instruction.dict())
    for unit in units:
        if unit.fcm_token:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=f"Dispatch for Event {event.eventId}",
                    body=f"Action: {action}, Location: {event.location}"
                ),
                token=unit.fcm_token
            )
            try:
                messaging.send(message)
                logger.info(f"FCM notification sent to unit: {unit.unitId}")
            except Exception as e:
                logger.error(f"Failed to send FCM to unit {unit.unitId}: {str(e)}")
    logger.info(f"Dispatch instruction sent for event: {event.eventId}, action: {action}")
    return instruction

# Pub/Sub callback
def callback(message):
    try:
        event_data = message.data.decode("utf-8")
        event = CriticalEvent.parse_raw(event_data)
        logger.info(f"Received event: {event.eventId}")
        action = action_mapper(event)
        units = unit_locator(event, action)
        instruction = dispatch_sender(event, action, units)
        message.ack()
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        message.nack()

# Start Pub/Sub subscription
def start_subscriber():
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    logger.info(f"Listening for messages on {subscription_path}...")
    try:
        streaming_pull_future.result()
    except Exception as e:
        streaming_pull_future.cancel()
        logger.error(f"Subscriber error: {str(e)}")

if __name__ == "__main__":
    # Initialize mock units
    mock_units = {
        "M1": {"unitId": "M1", "type": "medic", "status": "available", "location": "Zone Z2", "fcm_token": "mock-token-m1"},
        "F1": {"unitId": "F1", "type": "firefighter", "status": "available", "location": "Zone Z1", "fcm_token": "mock-token-f1"},
    }
    db_ref.child("field_units").set(mock_units)
    logger.info("Mock field units initialized")
    # Start subscriber
    start_subscriber()


##The dispatch works good and sends msgs to everyone directly to the members now we just need to add it to the summary agent and then on the dashboard