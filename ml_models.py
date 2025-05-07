import numpy as np
import pandas as pd
import logging
import pickle
import os
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from datetime import datetime, timedelta
from app import db
from models import TrafficData, PredictionResult, Intersection
from flask import current_app

logger = logging.getLogger(__name__)

# Global variables to store trained models
vehicle_count_model = None
congestion_model = None
model_features = ["vehicle_count", "average_speed", "queue_length", "wait_time", 
                 "hour_of_day", "day_of_week", "is_weekend", "is_peak_hour"]

def init_ml_models(app):
    """Initialize ML models for traffic prediction"""
    with app.app_context():
        logger.info("Initializing ML models")
        global vehicle_count_model, congestion_model
        
        # Check if models exist and load them
        if os.path.exists('vehicle_count_model.pkl'):
            try:
                with open('vehicle_count_model.pkl', 'rb') as f:
                    vehicle_count_model = pickle.load(f)
                logger.info("Loaded vehicle count model from file")
            except Exception as e:
                logger.error(f"Failed to load vehicle count model: {str(e)}")
        
        if os.path.exists('congestion_model.pkl'):
            try:
                with open('congestion_model.pkl', 'rb') as f:
                    congestion_model = pickle.load(f)
                logger.info("Loaded congestion model from file")
            except Exception as e:
                logger.error(f"Failed to load congestion model: {str(e)}")
        
        # If models don't exist, train them with available data
        if vehicle_count_model is None or congestion_model is None:
            # Check if we have enough data to train models
            data_count = TrafficData.query.count()
            
            if data_count > 100:  # Arbitrary threshold for minimal training data
                train_models()
            else:
                # Create simple baseline models if not enough data
                create_baseline_models()
                logger.info("Created baseline models (not enough data for training)")

def create_baseline_models():
    """Create simple baseline models when not enough data is available"""
    global vehicle_count_model, congestion_model
    
    # For vehicle count prediction, use a simple random forest with dummy data
    X_dummy = np.random.rand(100, len(model_features))
    y_dummy_count = np.random.randint(5, 50, 100)  # Random vehicle counts between 5-50
    
    vehicle_count_model = RandomForestRegressor(n_estimators=10, max_depth=3)
    vehicle_count_model.fit(X_dummy, y_dummy_count)
    
    # For congestion detection, also use random forest with dummy data
    y_dummy_congestion = np.random.choice([0, 1], 100, p=[0.7, 0.3])  # 30% congestion probability
    
    congestion_model = RandomForestClassifier(n_estimators=10, max_depth=3)
    congestion_model.fit(X_dummy, y_dummy_congestion)
    
    # Save the baseline models
    with open('vehicle_count_model.pkl', 'wb') as f:
        pickle.dump(vehicle_count_model, f)
    
    with open('congestion_model.pkl', 'wb') as f:
        pickle.dump(congestion_model, f)

def train_models():
    """Train ML models using historical traffic data"""
    global vehicle_count_model, congestion_model
    
    try:
        # Get historical data (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        traffic_data = TrafficData.query.filter(TrafficData.timestamp >= cutoff_time).all()
        
        if len(traffic_data) < 100:
            logger.warning(f"Only {len(traffic_data)} data points available, using baseline models")
            create_baseline_models()
            return
        
        # Prepare training data
        df = pd.DataFrame([{
            'vehicle_count': data.vehicle_count,
            'average_speed': data.average_speed,
            'queue_length': data.queue_length,
            'wait_time': data.wait_time,
            'direction': data.direction,
            'intersection_id': data.intersection_id,
            'timestamp': data.timestamp
        } for data in traffic_data])
        
        # Feature engineering
        df['hour_of_day'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['is_weekend'] = df['day_of_week'].apply(lambda x: 1 if x >= 5 else 0)
        df['is_peak_hour'] = df['hour_of_day'].apply(lambda x: 1 if (7 <= x < 10) or (16 <= x < 19) else 0)
        
        # Define congestion based on wait time and queue length
        # This is a simplification - in a real system, this would be more complex
        df['is_congested'] = ((df['wait_time'] > 45) & (df['queue_length'] > 10)).astype(int)
        
        # Prepare features and target variables
        X = df[model_features].values
        y_count = df['vehicle_count'].values
        y_congestion = df['is_congested'].values
        
        # Train vehicle count prediction model
        vehicle_count_model = RandomForestRegressor(n_estimators=50, max_depth=10, random_state=42)
        vehicle_count_model.fit(X, y_count)
        
        # Train congestion detection model
        congestion_model = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42)
        congestion_model.fit(X, y_congestion)
        
        # Save the trained models
        with open('vehicle_count_model.pkl', 'wb') as f:
            pickle.dump(vehicle_count_model, f)
        
        with open('congestion_model.pkl', 'wb') as f:
            pickle.dump(congestion_model, f)
        
        logger.info("Successfully trained ML models with historical data")
        
    except Exception as e:
        logger.error(f"Error training ML models: {str(e)}")
        create_baseline_models()

def predict_traffic(intersection_id, prediction_window=15):
    """Make traffic predictions for a specific intersection"""
    try:
        # Get recent traffic data
        cutoff_time = datetime.now() - timedelta(minutes=30)
        recent_data = TrafficData.query.filter(
            TrafficData.intersection_id == intersection_id,
            TrafficData.timestamp >= cutoff_time
        ).order_by(TrafficData.timestamp.desc()).all()
        
        if not recent_data:
            return {"error": "Not enough recent data for prediction"}
        
        # Get the intersection
        intersection = Intersection.query.get(intersection_id)
        if not intersection:
            return {"error": "Intersection not found"}
        
        # Group data by direction
        directions = set(data.direction for data in recent_data)
        predictions = []
        
        for direction in directions:
            # Get most recent data point for this direction
            direction_data = [d for d in recent_data if d.direction == direction]
            if not direction_data:
                continue
            
            latest_data = direction_data[0]
            
            # Prepare features for prediction
            now = datetime.now()
            hour_of_day = now.hour
            day_of_week = now.weekday()
            is_weekend = 1 if day_of_week >= 5 else 0
            is_peak_hour = 1 if (7 <= hour_of_day < 10) or (16 <= hour_of_day < 19) else 0
            
            features = np.array([[
                latest_data.vehicle_count,
                latest_data.average_speed,
                latest_data.queue_length,
                latest_data.wait_time,
                hour_of_day,
                day_of_week,
                is_weekend,
                is_peak_hour
            ]])
            
            # Make predictions using both models
            if vehicle_count_model and congestion_model:
                predicted_count = int(vehicle_count_model.predict(features)[0])
                congestion_prob = congestion_model.predict_proba(features)[0][1]  # Probability of class 1 (congested)
                predicted_congestion = congestion_prob > 0.5
                
                # Store prediction in database
                prediction = PredictionResult(
                    intersection_id=intersection_id,
                    prediction_window=prediction_window,
                    predicted_vehicle_count=predicted_count,
                    predicted_congestion=predicted_congestion,
                    confidence=float(congestion_prob),
                    direction=direction
                )
                db.session.add(prediction)
                
                predictions.append({
                    'direction': direction,
                    'predicted_vehicle_count': predicted_count,
                    'predicted_congestion': predicted_congestion,
                    'confidence': float(congestion_prob),
                    'prediction_window': prediction_window
                })
        
        db.session.commit()
        return {
            'intersection_id': intersection_id,
            'intersection_name': intersection.name,
            'timestamp': datetime.now().isoformat(),
            'predictions': predictions
        }
        
    except Exception as e:
        logger.error(f"Error making traffic predictions: {str(e)}")
        db.session.rollback()
        return {"error": str(e)}

def get_recent_predictions(intersection_id=None, minutes=30):
    """Get recent predictions for one or all intersections"""
    try:
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        if intersection_id:
            predictions = PredictionResult.query.filter(
                PredictionResult.intersection_id == intersection_id,
                PredictionResult.timestamp >= cutoff_time
            ).order_by(PredictionResult.timestamp.desc()).all()
        else:
            predictions = PredictionResult.query.filter(
                PredictionResult.timestamp >= cutoff_time
            ).order_by(PredictionResult.timestamp.desc()).all()
        
        return [p.to_dict() for p in predictions]
    
    except Exception as e:
        logger.error(f"Error getting recent predictions: {str(e)}")
        return {"error": str(e)}

def evaluate_model_accuracy():
    """Evaluate the accuracy of ML models using recent data"""
    try:
        # Get predictions from the last hour
        cutoff_time = datetime.now() - timedelta(hours=1)
        predictions = PredictionResult.query.filter(
            PredictionResult.timestamp >= cutoff_time
        ).all()
        
        if not predictions:
            return {"error": "No recent predictions available for evaluation"}
        
        # For each prediction, get the actual data from when the prediction window elapsed
        results = []
        for pred in predictions:
            # Calculate when the prediction was for
            target_time = pred.timestamp + timedelta(minutes=pred.prediction_window)
            
            # Skip predictions that haven't materialized yet
            if target_time > datetime.now():
                continue
            
            # Get actual data closest to the target time
            actual_data = TrafficData.query.filter(
                TrafficData.intersection_id == pred.intersection_id,
                TrafficData.direction == pred.direction,
                TrafficData.timestamp >= target_time - timedelta(minutes=2),
                TrafficData.timestamp <= target_time + timedelta(minutes=2)
            ).order_by(abs(db.func.julianday(TrafficData.timestamp) - db.func.julianday(target_time))).first()
            
            if not actual_data:
                continue
            
            # Calculate prediction error and accuracy
            count_error = abs(pred.predicted_vehicle_count - actual_data.vehicle_count)
            count_accuracy = max(0, 1 - (count_error / max(1, actual_data.vehicle_count)))
            
            # For congestion, determine if actual data showed congestion
            actual_congestion = (actual_data.wait_time > 45) and (actual_data.queue_length > 10)
            congestion_correct = (pred.predicted_congestion == actual_congestion)
            
            results.append({
                'intersection_id': pred.intersection_id,
                'direction': pred.direction,
                'prediction_time': pred.timestamp.isoformat(),
                'target_time': target_time.isoformat(),
                'predicted_count': pred.predicted_vehicle_count,
                'actual_count': actual_data.vehicle_count,
                'count_accuracy': count_accuracy,
                'predicted_congestion': pred.predicted_congestion,
                'actual_congestion': actual_congestion,
                'congestion_correct': congestion_correct
            })
        
        # Calculate overall accuracy
        if not results:
            return {"error": "No completed predictions available for evaluation"}
        
        count_accuracy = sum(r['count_accuracy'] for r in results) / len(results)
        congestion_accuracy = sum(1 for r in results if r['congestion_correct']) / len(results)
        
        return {
            'count_accuracy': count_accuracy,
            'congestion_accuracy': congestion_accuracy,
            'total_evaluated': len(results),
            'detailed_results': results
        }
        
    except Exception as e:
        logger.error(f"Error evaluating model accuracy: {str(e)}")
        return {"error": str(e)}
