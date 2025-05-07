from app import db
from datetime import datetime

class Intersection(db.Model):
    """Intersection model representing a traffic junction"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location_lat = db.Column(db.Float, nullable=False)
    location_lng = db.Column(db.Float, nullable=False)
    num_roads = db.Column(db.Integer, default=4)  # Number of roads meeting at this intersection
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    traffic_signals = db.relationship('TrafficSignal', backref='intersection', lazy=True)
    traffic_data = db.relationship('TrafficData', backref='intersection', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'location': {'lat': self.location_lat, 'lng': self.location_lng},
            'num_roads': self.num_roads,
            'signals': [signal.to_dict() for signal in self.traffic_signals]
        }


class TrafficSignal(db.Model):
    """Traffic signal for a specific direction at an intersection"""
    id = db.Column(db.Integer, primary_key=True)
    intersection_id = db.Column(db.Integer, db.ForeignKey('intersection.id'), nullable=False)
    direction = db.Column(db.String(20), nullable=False)  # N, S, E, W, NE, etc.
    current_state = db.Column(db.String(20), default='red')  # red, yellow, green
    default_cycle_time = db.Column(db.Integer, default=60)  # in seconds
    current_cycle_time = db.Column(db.Integer, default=60)  # in seconds
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'direction': self.direction,
            'state': self.current_state,
            'cycle_time': self.current_cycle_time,
            'last_updated': self.last_updated.isoformat()
        }


class TrafficData(db.Model):
    """Traffic data collected at an intersection"""
    id = db.Column(db.Integer, primary_key=True)
    intersection_id = db.Column(db.Integer, db.ForeignKey('intersection.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    vehicle_count = db.Column(db.Integer, default=0)
    average_speed = db.Column(db.Float, default=0.0)  # in km/h
    queue_length = db.Column(db.Integer, default=0)  # in number of vehicles
    wait_time = db.Column(db.Float, default=0.0)  # in seconds
    direction = db.Column(db.String(20), nullable=False)  # N, S, E, W, NE, etc.
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'vehicle_count': self.vehicle_count,
            'average_speed': self.average_speed,
            'queue_length': self.queue_length,
            'wait_time': self.wait_time,
            'direction': self.direction
        }


class Scenario(db.Model):
    """Pre-configured traffic scenarios for demonstration"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    duration = db.Column(db.Integer, default=180)  # in seconds
    config = db.Column(db.Text)  # JSON configuration for the scenario
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'duration': self.duration,
            'config': self.config
        }


class PredictionResult(db.Model):
    """Stores ML prediction results for traffic conditions"""
    id = db.Column(db.Integer, primary_key=True)
    intersection_id = db.Column(db.Integer, db.ForeignKey('intersection.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    prediction_window = db.Column(db.Integer, default=15)  # in minutes
    predicted_vehicle_count = db.Column(db.Integer)
    predicted_congestion = db.Column(db.Boolean, default=False)
    confidence = db.Column(db.Float)  # between 0 and 1
    direction = db.Column(db.String(20), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'prediction_window': self.prediction_window,
            'predicted_vehicle_count': self.predicted_vehicle_count,
            'predicted_congestion': self.predicted_congestion,
            'confidence': self.confidence,
            'direction': self.direction
        }


class PerformanceMetric(db.Model):
    """Performance metrics for traffic management scenarios"""
    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey('scenario.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    avg_wait_time = db.Column(db.Float)  # in seconds
    throughput = db.Column(db.Integer)  # vehicles processed
    congestion_duration = db.Column(db.Float)  # in seconds
    emergency_response_time = db.Column(db.Float)  # in seconds
    
    def to_dict(self):
        return {
            'id': self.id,
            'scenario_id': self.scenario_id,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'avg_wait_time': self.avg_wait_time,
            'throughput': self.throughput,
            'congestion_duration': self.congestion_duration,
            'emergency_response_time': self.emergency_response_time
        }
