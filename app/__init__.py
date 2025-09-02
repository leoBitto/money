# app/__init__.py
from flask import Flask, request, redirect, url_for
from flask_login import LoginManager, UserMixin, current_user
from scripts import config
from .filters import register_filters

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

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
    login_manager.login_view = "auth.login"

    @app.before_request
    def require_login():
        allowed_routes = ["auth.login", "static"]
        if not current_user.is_authenticated and request.endpoint not in allowed_routes:
            return redirect(url_for("auth.login"))

    # === Logging setup ===
    os.makedirs("logs", exist_ok=True)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # File handler con rotazione giornaliera
    file_handler = TimedRotatingFileHandler("logs/app.log", when="midnight", interval=1)
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(formatter)

    # Stream handler per stdout (va su journalctl)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    # Associa i due handler al logger principale di Flask
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(stream_handler)
    # =======================

    # Importa blueprint
    from app.auth import auth_bp
    from app.views import views_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)

    register_filters(app)

    return app
