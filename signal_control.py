import logging
import random
from datetime import datetime, timedelta
from flask import current_app
from app import db
from models import TrafficSignal, TrafficData, Intersection
from simulation import emergency_vehicles

logger = logging.getLogger(__name__)

# Global variables for signal control
signal_update_counter = 0
emergency_priority = False

def init_signal_control(app, socketio):
    """Initialize the traffic signal control system"""
    logger.info("Initializing signal control system")
    
    @socketio.on('update_signals')
    def handle_update_signals():
        """Socket event handler for updating signals"""
        with app.app_context():
            result = update_traffic_signals()
            socketio.emit('signals_updated', result)

def update_traffic_signals():
    """Update traffic signals based on current traffic conditions and ML predictions"""
    global signal_update_counter, emergency_priority
    signal_update_counter += 1
    
    try:
        # Only run complete logic every 5 seconds to avoid too frequent updates
        if signal_update_counter % 5 != 0:
            return {"status": "skipped", "counter": signal_update_counter}
        
        # Process each intersection
        intersections = Intersection.query.all()
        updated_signals = []
        
        for intersection in intersections:
            # Check for emergency vehicles at this intersection
            has_emergency = any(ev['intersection_id'] == intersection.id for ev in emergency_vehicles)
            
            # Get current traffic signals for this intersection
            signals = TrafficSignal.query.filter_by(intersection_id=intersection.id).all()
            if not signals:
                continue
                
            # Get recent traffic data for this intersection
            cutoff_time = datetime.now() - timedelta(minutes=5)
            traffic_data = TrafficData.query.filter(
                TrafficData.intersection_id == intersection.id,
                TrafficData.timestamp >= cutoff_time
            ).order_by(TrafficData.timestamp.desc()).all()
            
            if not traffic_data:
                continue
            
            # Group traffic data by direction
            traffic_by_direction = {}
            for data in traffic_data:
                if data.direction not in traffic_by_direction:
                    traffic_by_direction[data.direction] = []
                traffic_by_direction[data.direction].append(data)
            
            # Calculate traffic metrics for each direction
            metrics = {}
            for direction, data_list in traffic_by_direction.items():
                if not data_list:
                    continue
                    
                # Use most recent data point
                latest = data_list[0]
                
                # Calculate priority score based on multiple factors
                wait_time_factor = min(1.0, latest.wait_time / 120.0)  # Normalize to max 120 seconds
                queue_factor = min(1.0, latest.queue_length / 20.0)  # Normalize to max 20 vehicles
                speed_factor = 1.0 - min(1.0, latest.average_speed / 60.0)  # Slower traffic gets higher priority
                
                # Combined priority score (0-1)
                priority = (0.4 * wait_time_factor + 0.4 * queue_factor + 0.2 * speed_factor)
                
                # Check for emergency vehicles in this direction
                direction_emergency = any(ev['intersection_id'] == intersection.id and 
                                         ev['direction'] == direction for ev in emergency_vehicles)
                
                if direction_emergency:
                    # Emergency vehicles get highest priority
                    priority = 1.0
                    emergency_priority = True
                
                metrics[direction] = {
                    "priority": priority,
                    "wait_time": latest.wait_time,
                    "queue_length": latest.queue_length,
                    "vehicle_count": latest.vehicle_count,
                    "has_emergency": direction_emergency
                }
            
            # Determine which signals should be green based on priorities
            if emergency_priority and has_emergency:
                # Emergency vehicle handling - give green to direction with emergency
                emergency_directions = [d for d, m in metrics.items() if m.get("has_emergency", False)]
                
                if emergency_directions:
                    # Set emergency direction to green, all others to red
                    for signal in signals:
                        if signal.direction in emergency_directions:
                            new_state = "green"
                            new_cycle = 30  # Shorter cycle during emergency
                        else:
                            new_state = "red"
                            new_cycle = 30
                        
                        if signal.current_state != new_state or signal.current_cycle_time != new_cycle:
                            signal.current_state = new_state
                            signal.current_cycle_time = new_cycle
                            signal.last_updated = datetime.now()
                            updated_signals.append(signal.to_dict())
                
                # Reset emergency priority after handling
                if not any(ev['intersection_id'] == intersection.id for ev in emergency_vehicles):
                    emergency_priority = False
            
            else:
                # Normal operation - balance based on traffic conditions
                # Sort directions by priority
                sorted_directions = sorted(metrics.keys(), key=lambda d: metrics[d]["priority"], reverse=True)
                
                if not sorted_directions:
                    continue
                
                # Get current green directions
                current_green = [s.direction for s in signals if s.current_state == "green"]
                
                # Determine if we need to change signals
                change_needed = False
                
                # Check if highest priority direction is not green
                if sorted_directions[0] not in current_green:
                    change_needed = True
                
                # Check if current green has been active too long
                if current_green:
                    green_signal = next((s for s in signals if s.direction == current_green[0]), None)
                    if green_signal:
                        time_since_update = datetime.now() - green_signal.last_updated
                        if time_since_update.total_seconds() > green_signal.current_cycle_time:
                            change_needed = True
                
                if change_needed or not current_green:
                    # Determine which directions get green (typically highest priority and possibly
                    # the opposing direction for four-way intersections)
                    new_green = [sorted_directions[0]]
                    
                    # Add opposing direction if it exists and not a high-traffic situation
                    if len(sorted_directions) > 1:
                        # For a 4-way intersection, opposing directions are typically 0-2 and 1-3
                        # This is a simplification - real systems would have more complex mapping
                        direction_mapping = {
                            "N": "S",
                            "S": "N",
                            "E": "W",
                            "W": "E"
                        }
                        
                        opposing = direction_mapping.get(sorted_directions[0])
                        if opposing in metrics and metrics[sorted_directions[0]]["priority"] < 0.8:
                            new_green.append(opposing)
                    
                    # Set the new signal states
                    for signal in signals:
                        if signal.direction in new_green:
                            new_state = "green"
                            # Adjust cycle time based on traffic volume
                            priority = metrics[signal.direction]["priority"]
                            new_cycle = int(30 + priority * 60)  # 30-90 seconds depending on priority
                        else:
                            new_state = "red"
                            new_cycle = 60  # Default cycle time for red
                        
                        # Handle yellow transition if changing from green to red
                        if signal.current_state == "green" and new_state == "red":
                            new_state = "yellow"
                            new_cycle = 5  # Short yellow phase
                        
                        if signal.current_state != new_state or signal.current_cycle_time != new_cycle:
                            signal.current_state = new_state
                            signal.current_cycle_time = new_cycle
                            signal.last_updated = datetime.now()
                            updated_signals.append(signal.to_dict())
        
        # Commit all changes
        db.session.commit()
        
        return {
            "status": "success", 
            "updated_count": len(updated_signals),
            "updated_signals": updated_signals
        }
        
    except Exception as e:
        logger.error(f"Error updating traffic signals: {str(e)}")
        db.session.rollback()
        return {"status": "error", "message": str(e)}

def get_signal_states(intersection_id=None):
    """Get current state of traffic signals"""
    try:
        if intersection_id:
            signals = TrafficSignal.query.filter_by(intersection_id=intersection_id).all()
        else:
            signals = TrafficSignal.query.all()
        
        return [signal.to_dict() for signal in signals]
    
    except Exception as e:
        logger.error(f"Error getting signal states: {str(e)}")
        return {"error": str(e)}

def manual_signal_override(intersection_id, direction, new_state, cycle_time=None):
    """Manually override a traffic signal"""
    try:
        signal = TrafficSignal.query.filter_by(
            intersection_id=intersection_id,
            direction=direction
        ).first()
        
        if not signal:
            return {"error": "Signal not found"}
        
        # Validate the new state
        if new_state not in ["red", "yellow", "green"]:
            return {"error": "Invalid signal state"}
        
        # Update signal
        signal.current_state = new_state
        if cycle_time:
            signal.current_cycle_time = max(5, min(180, cycle_time))  # Limit to 5-180 seconds
        signal.last_updated = datetime.now()
        
        # If setting one direction to green, set conflicting directions to red
        if new_state == "green":
            # Find conflicting signals
            conflicting = TrafficSignal.query.filter(
                TrafficSignal.intersection_id == intersection_id,
                TrafficSignal.direction != direction
            ).all()
            
            # Determine which directions conflict
            # In a typical 4-way intersection, N/S can be green together, and E/W can be green together
            non_conflicting = {"N": "S", "S": "N", "E": "W", "W": "E"}
            
            for other_signal in conflicting:
                # Skip non-conflicting directions
                if non_conflicting.get(direction) == other_signal.direction:
                    continue
                    
                # Set conflicting directions to red
                other_signal.current_state = "red"
                other_signal.last_updated = datetime.now()
        
        db.session.commit()
        
        return {
            "status": "success",
            "signal": signal.to_dict()
        }
        
    except Exception as e:
        logger.error(f"Error in manual signal override: {str(e)}")
        db.session.rollback()
        return {"error": str(e)}
