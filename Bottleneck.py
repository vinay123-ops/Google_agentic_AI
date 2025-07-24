// pip install Flask pytz

from flask import Flask, request, jsonify
import random
from datetime import datetime
import pytz

app = Flask(__name__)

# Configuration
DENSITY_THRESHOLD = 4.5  # people per square meter
CONFIDENCE_THRESHOLD = 0.8
LOCATIONS = ["Gate 1", "Gate 2", "Gate 3", "Main Entrance"]

def density_analyzer(data):
    """Analyze crowd density and return high-density zones."""
    density = data.get('density', 0)
    location = data.get('location', random.choice(LOCATIONS))
    return {
        'location': location,
        'density': density,
        'is_high_density': density > DENSITY_THRESHOLD
    }

def flow_predictor(data):
    """Stub for predicting crowd movement direction."""
    # For MVP, return random movement vector
    return {
        'direction': random.choice(['north', 'south', 'east', 'west']),
        'speed': random.uniform(0.5, 2.0)  # meters per second
    }

def bottleneck_detector(density_data, flow_data):
    """Detect potential bottlenecks based on density and flow."""
    if density_data['is_high_density']:
        severity = 'high' if density_data['density'] > DENSITY_THRESHOLD * 1.2 else 'medium'
        return {
            'event_type': 'bottleneck',
            'location': density_data['location'],
            'severity': severity,
            'confidence': random.uniform(CONFIDENCE_THRESHOLD, 0.95),
            'timestamp': datetime.now(pytz.UTC).isoformat()
        }
    return None

def event_emitter(event):
    """Format and return bottleneck event for Central MCP."""
    if event:
        return event
    return {'status': 'no_bottleneck_detected'}

@app.route('/process', methods=['POST'])
def process_crowd_data():
    """Process incoming crowd data and detect bottlenecks."""
    try:
        data = request.get_json()
        if not data or 'density' not in data:
            return jsonify({'error': 'Invalid input: density required'}), 400

        # Analyze density
        density_result = density_analyzer(data)
        
        # Predict flow (stub)
        flow_result = flow_predictor(data)
        
        # Detect bottleneck
        bottleneck_event = bottleneck_detector(density_result, flow_result)
        
        # Emit event
        result = event_emitter(bottleneck_event)
        
        return jsonify(result), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)