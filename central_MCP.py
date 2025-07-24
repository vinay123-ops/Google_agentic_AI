//Install these pip install flask requests


from flask import Flask, request, jsonify
import requests
import uuid
from datetime import datetime
import pytz
import json

app = Flask(__name__)

# Configuration
BOTTLENECK_MCP_URL = "http://localhost:5000/process"
RESPONSE_LOG = []  # In-memory storage for MVP
AGENT_TIMEOUT = 5  # Seconds for agent requests

def generate_event_id():
    """Generate a unique event ID."""
    return f"EVT-{str(uuid.uuid4())[:8]}"

def stub_anomaly_agent(payload):
    """Stub for Anomaly Agent: returns no anomaly for MVP."""
    return {"status": "no_anomaly_detected", "details": "Stub: No anomalies found"}

def stub_summary_agent(bottleneck_response, anomaly_response):
    """Stub for Summary Agent: generates a simple summary."""
    summary = "Crowd analysis completed."
    if bottleneck_response.get("event_type") == "bottleneck":
        summary = f"High crowd density at {bottleneck_response.get('location', 'unknown')}."
    return {"summary": summary}

def stub_dispatch_agent(bottleneck_response, anomaly_response):
    """Stub for Dispatch Agent: suggests actions based on bottleneck."""
    if bottleneck_response.get("event_type") == "bottleneck":
        return {"action": f"Send 2 personnel to {bottleneck_response.get('location', 'unknown')}."}
    return {"action": "No dispatch required."}

def stub_notification_agent(bottleneck_response, anomaly_response):
    """Stub for Notification Agent: formats public alert."""
    if bottleneck_response.get("event_type") == "bottleneck":
        return {"message": f"Public Alert: Temporary congestion near {bottleneck_response.get('location', 'unknown')}."}
    return {"message": "No alerts at this time."}

def route_to_bottleneck_agent(payload):
    """Route payload to Bottleneck MCP Server."""
    try:
        response = requests.post(BOTTLENECK_MCP_URL, json=payload, timeout=AGENT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": f"Bottleneck MCP failed: {str(e)}"}

def orchestrate_agents(payload):
    """Orchestrate calls to agents in sequence."""
    # Step 1: Parallel calls to Bottleneck and Anomaly (Anomaly is stubbed)
    bottleneck_response = route_to_bottleneck_agent(payload)
    anomaly_response = stub_anomaly_agent(payload)
    
    # Step 2: Summary depends on both
    summary_response = stub_summary_agent(bottleneck_response, anomaly_response)
    
    # Step 3: Dispatch and Notification depend on results
    dispatch_response = stub_dispatch_agent(bottleneck_response, anomaly_response)
    notification_response = stub_notification_agent(bottleneck_response, anomaly_response)
    
    return {
        "bottleneck": bottleneck_response,
        "anomaly": anomaly_response,
        "summary": summary_response,
        "dispatch": dispatch_response,
        "notification": notification_response
    }

def store_response(event_id, original_event, agent_responses):
    """Store the event and agent responses with timestamp."""
    log_entry = {
        "event_id": event_id,
        "event": original_event,
        "agent_responses": agent_responses,
        "timestamp": datetime.now(pytz.UTC).isoformat()
    }
    RESPONSE_LOG.append(log_entry)
    return log_entry

@app.route("/event", methods=["POST"])
def process_event():
    """Receive and process incoming crowd data event."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid input: JSON payload required"}), 400

        # Generate event ID and timestamp
        event_id = generate_event_id()
        timestamp = datetime.now(pytz.UTC).isoformat()
        
        # Orchestrate agent calls
        agent_responses = orchestrate_agents(data)
        
        # Store responses
        log_entry = store_response(event_id, data, agent_responses)
        
        # Prepare response
        response = {
            "status": "processed",
            "event_id": event_id,
            "timestamp": timestamp,
            "event": data,
            "agent_responses": agent_responses
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route("/logs", methods=["GET"])
def get_logs():
    """Return stored event logs for dashboard polling."""
    return jsonify({"logs": RESPONSE_LOG}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)


