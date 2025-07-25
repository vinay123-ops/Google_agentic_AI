from fastapi import FastAPI
from google.cloud import pubsub_v1
from firebase_admin import db, initialize_app, credentials
from google.cloud import storage
import json
import logging
import uuid
import datetime
import base64

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI
app = FastAPI(title="Bottleneck Agent")

# Google Cloud configs
PROJECT_ID = "your-gcp-project-id"
BUCKET_NAME = "your-bucket-name"
BOTTLENECK_TOPIC = "bottleneck-frames"
SUMMARY_TOPIC = "summary-events"

# Initialize Google Cloud clients
publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
initialize_app(cred, {'databaseURL': 'https://your-project.firebaseio.com'})
db_ref = db.reference("/bottlenecks")

# Placeholder for Vertex AI
async def analyze_with_vertex_ai(frame: str, zone: str):
    # TODO: Integrate Vertex AI AutoML Vision or custom model for crowd density estimation
    # Input: Base64 frame; Output: Density score and confidence
    return {
        "zone": zone,
        "crowd_density": 7.4,  # Mock value
        "confidence": 0.93,
        "timestamp": datetime.datetime.utcnow().isoformat() + 'Z'
    }

# Upload frame to Cloud Storage
async def upload_to_storage(frame: str, filename: str) -> str:
    blob = bucket.blob(f"bottleneck/{filename}")
    blob.upload_from_string(base64.b64decode(frame), content_type='image/jpeg')
    return blob.public_url

# Process frame from Pub/Sub
def callback(message):
    data = json.loads(message.data.decode('utf-8'))
    frame, camera_id, location, zone_id = data["frame"], data["camera_id"], data["location"], data["zone_id"]
    
    # Analyze frame
    result = asyncio.run(analyze_with_vertex_ai(frame, zone_id))
    
    # Store result in Firebase
    result.update({
        "status": "bottleneck" if result["crowd_density"] > 5.0 else "normal",
        "file_url": asyncio.run(upload_to_storage(frame, f"{uuid.uuid4()}.jpg")),
        "source": "bottleneck",
        "camera_id": camera_id,
        "location": location,
        "zone_id": zone_id
    })
    entry_id = str(uuid.uuid4())
    db_ref.child(entry_id).set(result)
    
    # Publish to Summary Agent
    summary_topic_path = publisher.topic_path(PROJECT_ID, SUMMARY_TOPIC)
    publisher.publish(summary_topic_path, json.dumps(result).encode('utf-8'))
    
    message.ack()

# Start Pub/Sub subscription
@app.on_event("startup")
async def start_subscription():
    subscription_path = subscriber.subscription_path(PROJECT_ID, "bottleneck-sub")
    subscriber.subscribe(subscription_path, callback=callback)
    logging.info("Bottleneck Agent subscribed to Pub/Sub")

@app.get("/health")
async def health():
    return {"status": "bottleneck agent alive"}