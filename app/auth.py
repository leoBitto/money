# app/auth.py
"""
Semplice sistema di autenticazione con password hash.
In produzione, considera di usare un database per gli utenti.
"""
import hashlib
import os
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.username = username
    
    @staticmethod
    def get(username):
        # Lista utenti hardcoded - in produzione usare DB
        valid_users = ['admin', 'trader', 'analyst']
        if username in valid_users:
            return User(username)
        return None
    
    @staticmethod
    def authenticate(username, password):
        """
        Autentica utente con password.
        Password di default: 'trading123' (cambiarla in produzione!)
        """
        user = User.get(username)
        if not user:
            return None
        
        # Hash della password con salt
        salt = os.environ.get('PASSWORD_SALT', 'default_salt_change_me')
        expected_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        
        # Password di default per tutti gli utenti (in produzione: DB lookup)
        default_password = 'trading123'
        default_hash = hashlib.sha256((default_password + salt).encode()).hexdigest()
        
        if expected_hash == default_hash:
            return user
        
        return None
