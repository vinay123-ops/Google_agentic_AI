import asyncio
import base64
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form
from google.cloud import pubsub_v1
from google.cloud import storage
import json
import logging
import ffmpeg

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI
app = FastAPI(title="Central MCP - Project Drishti")

# Google Cloud configs
PROJECT_ID = "your-gcp-project-id"  # Replace with your GCP project ID
BUCKET_NAME = "your-bucket-name"  # Replace with your Cloud Storage bucket
BOTTLENECK_TOPIC = "bottleneck-frames"
ANOMALY_TOPIC = "anomaly-frames"

# Initialize Google Cloud clients
publisher = pubsub_v1.PublisherClient()
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Frame extraction configs
FRAME_INTERVAL = 5  # seconds
TARGET_FPS = 1      # 1 frame per second

# Camera metadata
CAMERA_CONFIG = {
    "CAM_01": {"location": "Gate 1 - North Wing", "zone_id": "Z1"},
    "CAM_02": {"location": "Main Stage", "zone_id": "Z2"},
    "CAM_03": {"location": "South Wing Exit", "zone_id": "Z3"}
}

# Motion heuristic for frame prioritization
def is_high_motion(prev_frame, curr_frame, threshold=0.1):
    if prev_frame is None:
        return False
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(prev_gray, curr_gray)
    motion_score = np.mean(diff) / 255.0
    return motion_score > threshold

# Frame extraction with FFmpeg
def extract_frames(video_path: str, interval_sec: int, fps: int = TARGET_FPS) -> list:
    try:
        stream = ffmpeg.input(video_path)
        stream = stream.filter('fps', fps=fps)
        out, _ = stream.output('pipe:', format='image2pipe', pix_fmt='rgb24').run(capture_stdout=True)
        frames = []
        prev_frame = None
        for frame_data in out.split(b'\xff\xd8'):  # JPEG delimiter
            if not frame_data:
                continue
            frame = b'\xff\xd8' + frame_data
            img = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR)
            if prev_frame is None or is_high_motion(prev_frame, img):
                frames.append(base64.b64encode(frame).decode('utf-8'))
            prev_frame = img
        return frames
    except ffmpeg.Error as e:
        logging.error(f"FFmpeg error: {e}")
        return []

# Upload video to Cloud Storage
async def upload_to_storage(file: UploadFile, filename: str) -> str:
    blob = bucket.blob(f"videos/{filename}")
    blob.upload_from_file(file.file, content_type=file.content_type)
    return blob.public_url

# Publish frames to Pub/Sub
async def publish_frames(frames: list, camera_id: str, location: str, zone_id: str):
    bottleneck_topic_path = publisher.topic_path(PROJECT_ID, BOTTLENECK_TOPIC)
    anomaly_topic_path = publisher.topic_path(PROJECT_ID, ANOMALY_TOPIC)
    batch_size = len(frames)
    futures = []
    for i, frame in enumerate(frames):
        payload = {
            "frame": frame,
            "camera_id": camera_id,
            "location": location,
            "zone_id": zone_id
        }
        topic = anomaly_topic_path if i >= batch_size // 2 else bottleneck_topic_path  # Prioritize anomaly for later frames
        futures.append(publisher.publish(topic, json.dumps(payload).encode('utf-8')))
    await asyncio.gather(*futures)
    logging.info(f"Published {len(frames)} frames to Pub/Sub")

# Main ingest route
@app.post("/ingest")
async def ingest_video(
    file: UploadFile = File(...),
    camera_id: str = Form(...),
    location: str = Form(None),
    zone_id: str = Form(None)
):
    # Autofill metadata
    if camera_id in CAMERA_CONFIG:
        location = location or CAMERA_CONFIG[camera_id]["location"]
        zone_id = zone_id or CAMERA_CONFIG[camera_id]["zone_id"]

    # Save video to Cloud Storage
    video_url = await upload_to_storage(file, file.filename)

    # Extract frames
    frames = extract_frames(file.filename, FRAME_INTERVAL)

    # Publish frames to Pub/Sub
    await publish_frames(frames, camera_id, location, zone_id)

    return {
        "status": "Frames dispatched",
        "camera_id": camera_id,
        "location": location,
        "zone_id": zone_id,
        "video_url": video_url
    }

@app.get("/health")
async def health():
    return {"status": "central mcp alive"}