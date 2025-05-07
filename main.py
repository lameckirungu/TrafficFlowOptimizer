from app import app  # noqa: F401

if __name__ == "__main__":
    # Import routes here to avoid circular imports
    from routes import *
    app.run(host="0.0.0.0", port=5000, debug=True)
