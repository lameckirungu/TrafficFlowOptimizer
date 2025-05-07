import json
import random
import time
import numpy as np
import logging
from datetime import datetime, timedelta
from flask import current_app
from app import db, socketio
from models import Intersection, TrafficData, TrafficSignal

logger = logging.getLogger(__name__)

# Global variables
active_scenario = None
simulation_running = False
simulation_speed = 1.0  # Multiplier for simulation speed
emergency_vehicles = []

# Base traffic patterns
TRAFFIC_PATTERNS = {
    "morning_rush": {
        "peak_directions": ["S", "E"],  # To city center
        "base_vehicle_count": 40,
        "variation": 15,
        "avg_speed_range": (20, 60),
        "queue_multiplier": 0.7,
        "wait_time_base": 30
    },
    "evening_rush": {
        "peak_directions": ["N", "W"],  # From city center
        "base_vehicle_count": 35,
        "variation": 20,
        "avg_speed_range": (15, 50),
        "queue_multiplier": 0.8,
        "wait_time_base": 40
    },
    "normal": {
        "peak_directions": [],
        "base_vehicle_count": 15,
        "variation": 8,
        "avg_speed_range": (30, 70),
        "queue_multiplier": 0.4,
        "wait_time_base": 15
    },
    "night": {
        "peak_directions": [],
        "base_vehicle_count": 5,
        "variation": 3,
        "avg_speed_range": (40, 90),
        "queue_multiplier": 0.2,
        "wait_time_base": 5
    },
    "weekend": {
        "peak_directions": ["E", "W"],  # Shopping areas
        "base_vehicle_count": 25,
        "variation": 12,
        "avg_speed_range": (25, 65),
        "queue_multiplier": 0.5,
        "wait_time_base": 20
    }
}

# Default intersection data for initialization
DEFAULT_INTERSECTIONS = [
    {
        "name": "Main & Broadway",
        "location_lat": 40.7128,
        "location_lng": -74.0060,
        "num_roads": 4
    },
    {
        "name": "Central & Park",
        "location_lat": 40.7150,
        "location_lng": -74.0048,
        "num_roads": 4
    },
    {
        "name": "Liberty & Commerce",
        "location_lat": 40.7112,
        "location_lng": -74.0090,
        "num_roads": 3
    },
    {
        "name": "Jefferson & Madison",
        "location_lat": 40.7200,
        "location_lng": -74.0070,
        "num_roads": 4
    },
    {
        "name": "Oak & Maple",
        "location_lat": 40.7180,
        "location_lng": -74.0100,
        "num_roads": 4
    }
]

def init_simulation(app, socketio, scheduler):
    """Initialize the traffic simulation system"""
    with app.app_context():
        # Initialize intersections if none exist
        if Intersection.query.count() == 0:
            _create_default_intersections()
            logger.info("Created default intersections")
        
        # Initialize traffic signals if none exist
        if TrafficSignal.query.count() == 0:
            _create_default_signals()
            logger.info("Created default traffic signals")
        
        # Schedule the simulation update task
        scheduler.add_job(
            update_simulation,
            'interval',
            seconds=1,
            id='simulation_update',
            replace_existing=True
        )
        logger.info("Scheduled simulation update job")

def _create_default_intersections():
    """Create default intersections for the simulation"""
    for intersection_data in DEFAULT_INTERSECTIONS:
        intersection = Intersection(**intersection_data)
        db.session.add(intersection)
    db.session.commit()

def _create_default_signals():
    """Create default traffic signals for each intersection"""
    intersections = Intersection.query.all()
    for intersection in intersections:
        directions = ["N", "S", "E", "W"]
        if intersection.num_roads == 3:
            directions = directions[:3]  # Use first 3 directions for 3-way intersections
        
        for direction in directions:
            signal = TrafficSignal(
                intersection_id=intersection.id,
                direction=direction,
                current_state="red",
                default_cycle_time=60,
                current_cycle_time=60
            )
            db.session.add(signal)
    db.session.commit()

def update_simulation():
    """Update the traffic simulation and emit data via WebSocket"""
    if not simulation_running:
        return
    
    try:
        # Get current pattern based on time of day
        current_hour = datetime.now().hour
        if 7 <= current_hour < 10:
            pattern_key = "morning_rush"
        elif 16 <= current_hour < 19:
            pattern_key = "evening_rush"
        elif 22 <= current_hour < 5:
            pattern_key = "night"
        elif datetime.now().weekday() >= 5:  # Weekend
            pattern_key = "weekend"
        else:
            pattern_key = "normal"
        
        # Adjust pattern if scenario is active
        if active_scenario:
            pattern_key = active_scenario.get('pattern', pattern_key)
        
        pattern = TRAFFIC_PATTERNS[pattern_key]
        
        # Process each intersection
        intersections = Intersection.query.all()
        all_traffic_data = []
        
        for intersection in intersections:
            traffic_data_batch = []
            signals = {signal.direction: signal for signal in intersection.traffic_signals}
            
            for direction, signal in signals.items():
                # Generate traffic data based on pattern and signal state
                is_peak_direction = direction in pattern["peak_directions"]
                is_green = signal.current_state == "green"
                
                # Base vehicle count with directional adjustment
                base_count = pattern["base_vehicle_count"]
                if is_peak_direction:
                    base_count *= 1.5
                
                # Add randomness
                vehicle_count = max(0, int(base_count + random.uniform(-pattern["variation"], pattern["variation"])))
                
                # Calculate average speed based on signal state and traffic volume
                min_speed, max_speed = pattern["avg_speed_range"]
                if is_green:
                    avg_speed = random.uniform(min_speed * 1.2, max_speed)
                else:
                    avg_speed = random.uniform(min_speed * 0.5, min_speed * 1.2)
                
                # Queue length depends on vehicle count and if signal is red
                queue_multiplier = pattern["queue_multiplier"]
                if not is_green:
                    queue_multiplier *= 2
                queue_length = int(vehicle_count * queue_multiplier)
                
                # Wait time calculation
                base_wait = pattern["wait_time_base"]
                wait_time = base_wait
                if not is_green:
                    wait_time += signal.current_cycle_time / 2  # Average wait time in cycle
                
                # Check for emergency vehicles
                has_emergency = any(ev['intersection_id'] == intersection.id and 
                                   ev['direction'] == direction for ev in emergency_vehicles)
                
                if has_emergency:
                    # Emergency vehicles increase count slightly but primarily impact signal timing
                    vehicle_count += 1
                
                # Create new traffic data record
                traffic_data = TrafficData(
                    intersection_id=intersection.id,
                    vehicle_count=vehicle_count,
                    average_speed=avg_speed,
                    queue_length=queue_length,
                    wait_time=wait_time,
                    direction=direction
                )
                
                db.session.add(traffic_data)
                traffic_data_batch.append(traffic_data.to_dict())
            
            # Emit traffic data for this intersection
            socketio.emit('traffic_update', {
                'intersection_id': intersection.id,
                'traffic_data': traffic_data_batch
            })
            
            all_traffic_data.extend(traffic_data_batch)
        
        db.session.commit()
        
        # Also emit consolidated data for all intersections
        socketio.emit('all_traffic_data', all_traffic_data)
        
    except Exception as e:
        logger.error(f"Error in simulation update: {str(e)}")
        db.session.rollback()

def set_simulation_state(running=True, speed=1.0):
    """Set the simulation state (running/paused) and speed"""
    global simulation_running, simulation_speed
    simulation_running = running
    simulation_speed = max(0.1, min(10.0, speed))  # Clamp between 0.1x and 10x
    return {"running": simulation_running, "speed": simulation_speed}

def get_simulation_state():
    """Get the current simulation state"""
    return {"running": simulation_running, "speed": simulation_speed}

def add_emergency_vehicle(intersection_id, direction):
    """Add an emergency vehicle to the simulation"""
    global emergency_vehicles
    emergency_vehicles.append({
        'intersection_id': intersection_id,
        'direction': direction,
        'timestamp': datetime.now()
    })
    # Cleanup old emergency vehicles (older than 2 minutes)
    now = datetime.now()
    emergency_vehicles = [ev for ev in emergency_vehicles 
                         if 'timestamp' in ev and now - ev['timestamp'] < timedelta(minutes=2)]
    return {"emergency_vehicles": len(emergency_vehicles)}

def get_traffic_data(intersection_id=None, minutes=5):
    """Get recent traffic data for one or all intersections"""
    cutoff_time = datetime.now() - timedelta(minutes=minutes)
    
    if intersection_id:
        data = TrafficData.query.filter(
            TrafficData.intersection_id == intersection_id,
            TrafficData.timestamp >= cutoff_time
        ).order_by(TrafficData.timestamp.desc()).all()
    else:
        data = TrafficData.query.filter(
            TrafficData.timestamp >= cutoff_time
        ).order_by(TrafficData.timestamp.desc()).all()
    
    return [d.to_dict() for d in data]

def set_active_scenario(scenario_config):
    """Set the active scenario configuration"""
    global active_scenario
    active_scenario = scenario_config
    return {"success": True, "scenario": active_scenario}

def clear_active_scenario():
    """Clear the active scenario configuration"""
    global active_scenario
    active_scenario = None
    return {"success": True}
