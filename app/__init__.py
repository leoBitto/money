from flask import Flask
from flask_login import LoginManager, UserMixin
from scripts import config

login_manager = LoginManager()

# Mock "db" utenti
users = {config.USERNAME: {"password": config.PASSWORD}}

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    
    login_manager.init_app(app)

    # Importa blueprint
    from app.auth import auth_bp
    from app.views import views_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)

    return app
