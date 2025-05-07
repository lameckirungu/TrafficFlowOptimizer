import json
import logging
import random
from datetime import datetime, timedelta
from flask import current_app
from app import db, socketio
from models import Scenario, PerformanceMetric, Intersection, TrafficData
from simulation import set_simulation_state, set_active_scenario, add_emergency_vehicle, clear_active_scenario

logger = logging.getLogger(__name__)

# Global variables
active_scenario_id = None
scenario_start_time = None
scenario_metrics = {}

# Predefined scenario configurations for Nairobi, Kenya
DEFAULT_SCENARIOS = [
    {
        "name": "Normal Traffic Flow",
        "description": "Typical weekday traffic in Nairobi with moderate congestion during business hours",
        "duration": 180,  # 3 minutes for demo
        "config": json.dumps({
            "pattern": "normal",
            "emergency_vehicles": False,
            "simulation_speed": 2.0
        })
    },
    {
        "name": "Morning Rush Hour",
        "description": "Heavy traffic flowing into Nairobi Central Business District during morning peak hours",
        "duration": 180,
        "config": json.dumps({
            "pattern": "morning_rush",
            "emergency_vehicles": False,
            "simulation_speed": 2.0
        })
    },
    {
        "name": "Evening Rush Hour",
        "description": "Heavy traffic on Uhuru Highway and Moi Avenue during evening exodus from Nairobi CBD",
        "duration": 180,
        "config": json.dumps({
            "pattern": "evening_rush",
            "emergency_vehicles": False,
            "simulation_speed": 2.0
        })
    },
    {
        "name": "Weekend Shopping",
        "description": "Moderate traffic around Westlands and Ngong Road shopping areas during weekend",
        "duration": 180,
        "config": json.dumps({
            "pattern": "weekend",
            "emergency_vehicles": False,
            "simulation_speed": 2.0
        })
    },
    {
        "name": "Emergency Response",
        "description": "Test emergency vehicle priority through congested Nairobi intersections during rush hour",
        "duration": 180,
        "config": json.dumps({
            "pattern": "morning_rush",
            "emergency_vehicles": True,
            "emergency_interval": 30,  # Add emergency vehicle every 30 seconds
            "simulation_speed": 2.0
        })
    }
]

def init_scenarios(app, socketio, scheduler):
    """Initialize the traffic scenarios system"""
    with app.app_context():
        # Create default scenarios if none exist
        if Scenario.query.count() == 0:
            _create_default_scenarios()
            logger.info("Created default scenarios")
        
        # Schedule the scenario progress monitoring task
        scheduler.add_job(
            monitor_scenario_progress,
            'interval',
            seconds=5,
            id='scenario_monitor',
            replace_existing=True
        )
        logger.info("Scheduled scenario monitoring job")

def _create_default_scenarios():
    """Create default scenarios for demonstration"""
    for scenario_data in DEFAULT_SCENARIOS:
        scenario = Scenario(**scenario_data)
        db.session.add(scenario)
    db.session.commit()

def monitor_scenario_progress():
    """Monitor the progress of currently running scenario"""
    global active_scenario_id, scenario_start_time, scenario_metrics
    
    if not active_scenario_id or not scenario_start_time:
        return
    
    try:
        # Get the active scenario
        scenario = Scenario.query.get(active_scenario_id)
        if not scenario:
            clear_scenario()
            return
        
        # Check if scenario has expired
        elapsed = (datetime.now() - scenario_start_time).total_seconds()
        if elapsed >= scenario.duration:
            # End the scenario
            end_scenario()
            return
        
        # Update progress metrics
        _update_scenario_metrics()
        
        # For emergency vehicle scenario, add emergency vehicles periodically
        if active_scenario_id:
            scenario_config = json.loads(scenario.config)
            if scenario_config.get("emergency_vehicles", False):
                emergency_interval = scenario_config.get("emergency_interval", 60)
                if int(elapsed) % emergency_interval == 0:
                    _add_random_emergency_vehicle()
        
        # Emit progress update to clients
        progress_percent = min(100, int((elapsed / scenario.duration) * 100))
        remaining = max(0, scenario.duration - elapsed)
        
        socketio.emit('scenario_progress', {
            'scenario_id': scenario.id,
            'name': scenario.name,
            'progress': progress_percent,
            'elapsed': int(elapsed),
            'remaining': int(remaining),
            'metrics': scenario_metrics
        })
        
    except Exception as e:
        logger.error(f"Error monitoring scenario progress: {str(e)}")

def _update_scenario_metrics():
    """Update performance metrics for the active scenario"""
    global scenario_metrics
    
    try:
        # Get all intersections
        intersections = Intersection.query.all()
        
        # Calculate metrics across all intersections
        total_wait_time = 0
        total_vehicles = 0
        congested_intersections = 0
        
        for intersection in intersections:
            # Get latest traffic data
            latest_data = TrafficData.query.filter_by(intersection_id=intersection.id).order_by(
                TrafficData.timestamp.desc()
            ).limit(10).all()
            
            if not latest_data:
                continue
            
            # Calculate intersection metrics
            intersection_wait_time = sum(d.wait_time for d in latest_data) / len(latest_data)
            intersection_vehicles = sum(d.vehicle_count for d in latest_data)
            
            total_wait_time += intersection_wait_time
            total_vehicles += intersection_vehicles
            
            # Check if intersection is congested
            congestion_count = sum(1 for d in latest_data if d.wait_time > 45 and d.queue_length > 10)
            if congestion_count > len(latest_data) / 2:  # More than half of directions are congested
                congested_intersections += 1
        
        if intersections:
            avg_wait_time = total_wait_time / len(intersections)
        else:
            avg_wait_time = 0
        
        # Update the metrics
        scenario_metrics = {
            'avg_wait_time': round(avg_wait_time, 1),
            'total_vehicles': total_vehicles,
            'congested_intersections': congested_intersections,
            'total_intersections': len(intersections)
        }
        
    except Exception as e:
        logger.error(f"Error updating scenario metrics: {str(e)}")

def _add_random_emergency_vehicle():
    """Add a random emergency vehicle to simulation"""
    intersections = Intersection.query.all()
    if not intersections:
        return
    
    # Choose a random intersection
    intersection = random.choice(intersections)
    
    # Choose a random direction
    directions = ["N", "S", "E", "W"]
    if intersection.num_roads == 3:
        directions = directions[:3]
    
    direction = random.choice(directions)
    
    # Add the emergency vehicle
    add_emergency_vehicle(intersection.id, direction)
    
    # Notify clients
    socketio.emit('emergency_vehicle', {
        'intersection_id': intersection.id,
        'intersection_name': intersection.name,
        'direction': direction,
        'timestamp': datetime.now().isoformat()
    })

def start_scenario(scenario_id):
    """Start running a specific traffic scenario"""
    global active_scenario_id, scenario_start_time, scenario_metrics
    
    try:
        # Clear any active scenario
        if active_scenario_id:
            clear_scenario()
        
        # Get the requested scenario
        scenario = Scenario.query.get(scenario_id)
        if not scenario:
            return {"error": f"Scenario with ID {scenario_id} not found"}
        
        # Set the active scenario
        active_scenario_id = scenario_id
        scenario_start_time = datetime.now()
        scenario_metrics = {}
        
        # Parse configuration
        config = json.loads(scenario.config)
        
        # Configure simulation
        simulation_speed = config.get("simulation_speed", 1.0)
        set_simulation_state(running=True, speed=simulation_speed)
        
        # Set active scenario in simulation
        set_active_scenario(config)
        
        # Create performance metric entry
        metric = PerformanceMetric(
            scenario_id=scenario_id,
            start_time=scenario_start_time
        )
        db.session.add(metric)
        db.session.commit()
        
        return {
            "success": True,
            "scenario_id": scenario_id,
            "name": scenario.name,
            "start_time": scenario_start_time.isoformat(),
            "duration": scenario.duration
        }
        
    except Exception as e:
        logger.error(f"Error starting scenario: {str(e)}")
        db.session.rollback()
        clear_scenario()
        return {"error": str(e)}

def end_scenario():
    """End the currently running scenario and record metrics"""
    global active_scenario_id, scenario_start_time, scenario_metrics
    
    if not active_scenario_id:
        return {"error": "No active scenario"}
    
    try:
        # Get the scenario
        scenario = Scenario.query.get(active_scenario_id)
        if not scenario:
            clear_scenario()
            return {"error": "Scenario not found"}
        
        # Update performance metrics
        metric = PerformanceMetric.query.filter_by(
            scenario_id=active_scenario_id,
            end_time=None
        ).order_by(PerformanceMetric.start_time.desc()).first()
        
        if metric:
            metric.end_time = datetime.now()
            metric.avg_wait_time = scenario_metrics.get('avg_wait_time', 0)
            metric.throughput = scenario_metrics.get('total_vehicles', 0)
            metric.congestion_duration = 0  # Would need more detailed tracking
            
            # Calculate emergency response time if applicable
            # This would require tracking when emergency vehicles were added and when they cleared intersections
            metric.emergency_response_time = 0
            
            db.session.commit()
        
        # Clear the active scenario
        scenario_id = active_scenario_id
        clear_scenario()
        
        # Notify clients
        socketio.emit('scenario_completed', {
            'scenario_id': scenario_id,
            'name': scenario.name,
            'metrics': scenario_metrics
        })
        
        return {
            "success": True,
            "scenario_id": scenario_id,
            "name": scenario.name,
            "metrics": scenario_metrics
        }
        
    except Exception as e:
        logger.error(f"Error ending scenario: {str(e)}")
        db.session.rollback()
        clear_scenario()
        return {"error": str(e)}

def clear_scenario():
    """Clear the active scenario state"""
    global active_scenario_id, scenario_start_time, scenario_metrics
    
    active_scenario_id = None
    scenario_start_time = None
    scenario_metrics = {}
    
    # Reset simulation to normal state
    clear_active_scenario()
    
    return {"success": True}

def get_scenario_list():
    """Get list of available scenarios"""
    try:
        scenarios = Scenario.query.all()
        return [s.to_dict() for s in scenarios]
    
    except Exception as e:
        logger.error(f"Error getting scenario list: {str(e)}")
        return {"error": str(e)}

def get_scenario_metrics(scenario_id=None, limit=5):
    """Get metrics for completed scenario runs"""
    try:
        query = PerformanceMetric.query
        
        if scenario_id:
            query = query.filter_by(scenario_id=scenario_id)
        
        metrics = query.filter(PerformanceMetric.end_time != None).order_by(
            PerformanceMetric.start_time.desc()
        ).limit(limit).all()
        
        return [m.to_dict() for m in metrics]
    
    except Exception as e:
        logger.error(f"Error getting scenario metrics: {str(e)}")
        return {"error": str(e)}

def get_active_scenario():
    """Get information about the currently active scenario"""
    global active_scenario_id, scenario_start_time, scenario_metrics
    
    if not active_scenario_id or not scenario_start_time:
        return {"active": False}
    
    try:
        scenario = Scenario.query.get(active_scenario_id)
        if not scenario:
            clear_scenario()
            return {"active": False}
        
        elapsed = (datetime.now() - scenario_start_time).total_seconds()
        progress_percent = min(100, int((elapsed / scenario.duration) * 100))
        remaining = max(0, scenario.duration - elapsed)
        
        return {
            "active": True,
            "scenario_id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "progress": progress_percent,
            "elapsed": int(elapsed),
            "remaining": int(remaining),
            "metrics": scenario_metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting active scenario: {str(e)}")
        return {"active": False, "error": str(e)}
