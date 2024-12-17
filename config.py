import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Environment
    ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = ENV == 'development'
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24))
    
    # Database configuration
    DB_TYPE = os.getenv('DB_TYPE', 'sqlite')  # 'sqlite' or 'mongodb'
    
    # SQLite configuration
    SQLITE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                            'database.db' if ENV == 'development' else '/var/www/melanoma/database.db')
    
    # MongoDB configuration (if needed later)
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    
    # File upload configuration
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 
                             os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                        'uploads' if ENV == 'development' else '/var/www/melanoma/uploads'))
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Gemini API configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not found in environment variables")

    # Production specific settings
    if ENV == 'production':
        SESSION_COOKIE_SECURE = True
        SESSION_COOKIE_HTTPONLY = True
        PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
        
        # Logging
        LOG_FILE = '/var/log/melanoma/app.log'
