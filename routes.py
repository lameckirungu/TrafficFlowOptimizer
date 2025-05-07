import json
import logging
from datetime import datetime
from flask import render_template, request, jsonify
from app import app, socketio
from models import Intersection, TrafficData, TrafficSignal, Scenario, PredictionResult, PerformanceMetric
from simulation import (
    set_simulation_state, get_simulation_state, add_emergency_vehicle, 
    get_traffic_data
)
from ml_models import predict_traffic, get_recent_predictions, evaluate_model_accuracy
from signal_control import get_signal_states, manual_signal_override, update_traffic_signals
from scenarios import (
    start_scenario, end_scenario, clear_scenario, get_scenario_list,
    get_scenario_metrics, get_active_scenario
)

logger = logging.getLogger(__name__)

# Routes for main pages
@app.route('/')
def index():
    """Main dashboard page"""
    intersections = [i.to_dict() for i in Intersection.query.all()]
    active_scenario = get_active_scenario()
    return render_template('index.html', 
                           intersections=intersections, 
                           active_scenario=active_scenario)

@app.route('/scenarios')
def scenarios_page():
    """Scenarios management page"""
    scenarios = get_scenario_list()
    active_scenario = get_active_scenario()
    return render_template('scenarios.html', 
                           scenarios=scenarios, 
                           active_scenario=active_scenario)

@app.route('/analytics')
def analytics_page():
    """Analytics and model performance page"""
    intersections = [i.to_dict() for i in Intersection.query.all()]
    metrics = get_scenario_metrics()
    return render_template('analytics.html', 
                           intersections=intersections,
                           metrics=metrics)

# API Routes for Simulation Control
@app.route('/api/simulation/state', methods=['GET', 'POST'])
def simulation_state():
    """Get or set simulation state"""
    if request.method == 'POST':
        data = request.get_json()
        running = data.get('running', True)
        speed = data.get('speed', 1.0)
        result = set_simulation_state(running=running, speed=speed)
        return jsonify(result)
    else:
        return jsonify(get_simulation_state())

@app.route('/api/simulation/emergency', methods=['POST'])
def emergency_vehicle():
    """Add emergency vehicle to simulation"""
    data = request.get_json()
    intersection_id = data.get('intersection_id')
    direction = data.get('direction')
    
    if not intersection_id or not direction:
        return jsonify({"error": "Missing required parameters"}), 400
    
    result = add_emergency_vehicle(intersection_id, direction)
    return jsonify(result)

@app.route('/api/traffic/data')
def traffic_data():
    """Get recent traffic data"""
    intersection_id = request.args.get('intersection_id', type=int)
    minutes = request.args.get('minutes', 5, type=int)
    data = get_traffic_data(intersection_id=intersection_id, minutes=minutes)
    return jsonify(data)

# API Routes for ML Predictions
@app.route('/api/predictions/traffic')
def traffic_prediction():
    """Get traffic predictions for an intersection"""
    intersection_id = request.args.get('intersection_id', type=int)
    window = request.args.get('window', 15, type=int)
    
    if not intersection_id:
        return jsonify({"error": "Missing intersection_id parameter"}), 400
        
    result = predict_traffic(intersection_id, prediction_window=window)
    return jsonify(result)

@app.route('/api/predictions/recent')
def recent_predictions():
    """Get recent traffic predictions"""
    intersection_id = request.args.get('intersection_id', type=int)
    minutes = request.args.get('minutes', 30, type=int)
    data = get_recent_predictions(intersection_id=intersection_id, minutes=minutes)
    return jsonify(data)

@app.route('/api/predictions/accuracy')
def prediction_accuracy():
    """Get accuracy metrics for predictions"""
    result = evaluate_model_accuracy()
    return jsonify(result)

# API Routes for Signal Control
@app.route('/api/signals/state')
def signal_state():
    """Get current state of traffic signals"""
    intersection_id = request.args.get('intersection_id', type=int)
    data = get_signal_states(intersection_id=intersection_id)
    return jsonify(data)

@app.route('/api/signals/override', methods=['POST'])
def override_signal():
    """Manually override a traffic signal"""
    data = request.get_json()
    intersection_id = data.get('intersection_id')
    direction = data.get('direction')
    new_state = data.get('state')
    cycle_time = data.get('cycle_time')
    
    if not intersection_id or not direction or not new_state:
        return jsonify({"error": "Missing required parameters"}), 400
    
    result = manual_signal_override(intersection_id, direction, new_state, cycle_time)
    return jsonify(result)

@app.route('/api/signals/update', methods=['POST'])
def update_signals():
    """Trigger an update of traffic signals"""
    result = update_traffic_signals()
    return jsonify(result)

# API Routes for Scenarios
@app.route('/api/scenarios/list')
def list_scenarios():
    """Get list of available scenarios"""
    scenarios = get_scenario_list()
    return jsonify(scenarios)

@app.route('/api/scenarios/start', methods=['POST'])
def start_scenario_route():
    """Start a specific scenario"""
    data = request.get_json()
    scenario_id = data.get('scenario_id')
    
    if not scenario_id:
        return jsonify({"error": "Missing scenario_id parameter"}), 400
    
    result = start_scenario(scenario_id)
    return jsonify(result)

@app.route('/api/scenarios/end', methods=['POST'])
def end_scenario_route():
    """End the current scenario"""
    result = end_scenario()
    return jsonify(result)

@app.route('/api/scenarios/clear', methods=['POST'])
def clear_scenario_route():
    """Clear the current scenario state"""
    result = clear_scenario()
    return jsonify(result)

@app.route('/api/scenarios/active')
def active_scenario_route():
    """Get information about the currently active scenario"""
    result = get_active_scenario()
    return jsonify(result)

@app.route('/api/scenarios/metrics')
def scenario_metrics_route():
    """Get metrics for scenarios"""
    scenario_id = request.args.get('scenario_id', type=int)
    limit = request.args.get('limit', 5, type=int)
    data = get_scenario_metrics(scenario_id=scenario_id, limit=limit)
    return jsonify(data)

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    # Send initial data to the client
    active_scenario = get_active_scenario()
    socketio.emit('active_scenario', active_scenario, room=request.sid)
    
    simulation_state = get_simulation_state()
    socketio.emit('simulation_state', simulation_state, room=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('request_data_update')
def handle_data_request(data):
    """Handle client request for data update"""
    intersection_id = data.get('intersection_id')
    traffic_data = get_traffic_data(intersection_id=intersection_id, minutes=5)
    signal_states = get_signal_states(intersection_id=intersection_id)
    
    socketio.emit('data_update', {
        'traffic_data': traffic_data,
        'signal_states': signal_states
    }, room=request.sid)

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {str(e)}")
    return render_template('500.html'), 500
