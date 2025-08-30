from app import create_app
from flask_login import LoginManager
import logging

app = create_app()

if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Starting Trading Dashboard...")
    print("📝 Default login: admin / trading123")
    print("🔐 Change password in production!")
    
    app.run(debug=True, host='0.0.0.0', port=5000)