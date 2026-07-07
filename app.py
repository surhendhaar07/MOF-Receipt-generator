from flask import Flask
import os
from models.database import init_db
from routes.main import main_bp

def create_app():
    app = Flask(__name__)
    
    # Configure workspace directories
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config['DATABASE'] = os.path.join(base_dir, 'receipt.db')
    app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'uploads')
    app.config['RECEIPTS_FOLDER'] = os.path.join(base_dir, 'generated_receipts')
    
    # Ensure temporary and storage directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RECEIPTS_FOLDER'], exist_ok=True)
    
    # Initialize SQLite schema and counter
    init_db(app.config['DATABASE'])
    
    # Register blueprints
    app.register_blueprint(main_bp)
    
    return app

if __name__ == '__main__':
    app = create_app()
    # Run Flask development server locally on port 5000
    print("Makkalil Oruvan Foundation Receipt Generator starting...")
    app.run(debug=True, host='127.0.0.1', port=5000)
