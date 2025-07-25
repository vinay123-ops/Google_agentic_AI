from fastapi import FastAPI
from google.cloud import pubsub_v1
from firebase_admin import db, initialize_app, credentials
from google.cloud import storage
import json
import logging
import uuid
import datetime
import cv2
import numpy as np
from collections import deque

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI
app = FastAPI(title="Anomaly Agent")

# Google Cloud configs
PROJECT_ID = "your-gcp-project-id"
BUCKET_NAME = "your-bucket-name"
ANOMALY_TOPIC = "anomaly-frames"
SUMMARY_TOPIC = "summary-events"

# Initialize Google Cloud clients
publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
initialize_app(cred, {'databaseURL': 'https://your-project.firebaseio.com'})
db_ref = db.reference("/verified_alerts")

# Sliding frame buffer
frame_buffer = deque(maxlen=10)

# Placeholder for Vertex AI
async def analyze_with_vertex_ai(frame: str, camera_id: str):
    # TODO: Integrate Vertex AI Vision API or custom model for anomaly detection
    # Input: Base64 frame; Output: List of detected labels (e.g., ["smoke", "fire"])
    img_data = base64.b64decode(frame)
    img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
    # Mock labels for skeleton
    labels = ["smoke"] if np.random.rand() > 0.8 else []
    return labels

# Upload frame to Cloud Storage
async def upload_to_storage(frame: str, filename: str) -> str:
    blob = bucket.blob(f"anomalies/{filename}")
    blob.upload_from_string(base64.b64decode(frame), content_type='image/jpeg')
    return blob.public_url

# Process frame from Pub/Sub
def callback(message):
    data = json.loads(message.data.decode('utf-8'))
    frame, camera_id, location, zone_id = data["frame"], data["camera_id"], data["location"], data["zone_id"]
    
    # Add to buffer
    frame_buffer.append(frame)
    
    # Analyze frame
    labels = asyncio.run(analyze_with_vertex_ai(frame, camera_id))
    threat_keywords = ['smoke', 'fire', 'weapon', 'gun', 'knife', 'crowd']
    
    if any(keyword in label.lower() for label in labels for keyword in threat_keywords):
        # Store alert in Firebase
        alert = {
            "image_url": asyncio.run(upload_to_storage(frame, f"{uuid.uuid4()}.jpg")),
            "message": f"Verified Threat: {labels[0]}",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "camera_id": camera_id,
            "location": location,
            "zone_id": zone_id
        }
        db_ref.push(alert)
        
        # Analyze buffer for additional context
        for buffered_frame in frame_buffer:
            buffered_labels = asyncio.run(analyze_with_vertex_ai(buffered_frame, camera_id))
            if any(keyword in label.lower() for label in buffered_labels for keyword in threat_keywords):
                db_ref.push({
                    "image_url": asyncio.run(upload_to_storage(buffered_frame, f"{uuid.uuid4()}.jpg")),
                    "message": f"Buffered Threat: {buffered_labels[0]}",
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "camera_id": camera_id,
                    "location": location,
                    "zone_id": zone_id
                })
        
        # Publish to Summary Agent
        summary_topic_path = publisher.topic_path(PROJECT_ID, SUMMARY_TOPIC)
        publisher.publish(summary_topic_path, json.dumps(alert).encode('utf-8'))
    
    message.ack()

# Start Pub/Sub subscription
@app.on_event("startup")
async def start_subscription():
    subscription_path = subscriber.subscription_path(PROJECT_ID, "anomaly-sub")
    subscriber.subscribe(subscription_path, callback=callback)
    logging.info("Anomaly Agent subscribed to Pub/Sub")

@app.get("/health")
async def health():
    return {"status": "anomaly agent alive"}