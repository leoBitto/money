 app/__init__.py
from flask import Flask
from flask_login import LoginManager
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    # Login Manager setup
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access the trading dashboard.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.auth import User
        return User.get(user_id)
    
    # Register Blueprints
    from app.routes.main import main_bp
    from app.routes.portfolio import portfolio_bp
    from app.routes.signals import signals_bp
    from app.routes.backtest import backtest_bp
    from app.routes.query import query_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    from app.routes.auth import auth_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(portfolio_bp, url_prefix='/portfolio')
    app.register_blueprint(signals_bp, url_prefix='/signals')
    app.register_blueprint(backtest_bp, url_prefix='/backtest')
    app.register_blueprint(query_bp, url_prefix='/query')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    return app
