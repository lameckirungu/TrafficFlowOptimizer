import os
import logging
from flask import Flask
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from apscheduler.schedulers.background import BackgroundScheduler

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
socketio = SocketIO()
scheduler = BackgroundScheduler()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "traffic_management_secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///traffic_management.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the app with extensions
db.init_app(app)
socketio.init_app(app, cors_allowed_origins="*")

# Start the scheduler
scheduler.start()

# Initialize database
with app.app_context():
    # Import models to create tables
    import models  # noqa: F401
    db.create_all()
    logger.info("Database tables created")

# Import and initialize simulation, ML models, and signal control
from simulation import init_simulation
from ml_models import init_ml_models
from signal_control import init_signal_control
from scenarios import init_scenarios

with app.app_context():
    init_simulation(app, socketio, scheduler)
    init_ml_models(app)
    init_signal_control(app, socketio)
    init_scenarios(app, socketio, scheduler)
    
    # Import routes
    import routes  # noqa: F401
    
    logger.info("All components initialized")
