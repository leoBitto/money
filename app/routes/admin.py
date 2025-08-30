# app/routes/admin.py
from flask import Blueprint, render_template, jsonify
from flask_login import login_required

from scripts.database import execute_query
from scripts.portfolio import create_portfolio_tables

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/')
@login_required
def index():
    """Pagina amministrativa per gestione sistema"""
    try:
        # Statistiche database
        stats_queries = {
            'total_records': "SELECT COUNT(*) FROM universe",
            'unique_tickers': "SELECT COUNT(DISTINCT ticker) FROM universe",
            'date_range': "SELECT MIN(date), MAX(date) FROM universe",
            'last_update': "SELECT MAX(date) FROM universe",
            'portfolios_count': "SELECT COUNT(DISTINCT portfolio_name) FROM portfolio_snapshots"
        }
        
        stats = {}
        for stat_name, query in stats_queries.items():
            try:
                result = execute_query(query)
                stats[stat_name] = result[0] if result else None
            except:
                stats[stat_name] = "Error"
        
        return render_template("admin/index.html", stats=stats)
    
    except Exception as e:
        return render_template("admin/index.html", error=str(e))

@admin_bp.route('/init_portfolio_tables', methods=['POST'])
@login_required
def init_portfolio_tables():
    """Inizializza tabelle portfolio"""
    try:
        create_portfolio_tables()
        return jsonify({'success': True, 'message': 'Portfolio tables initialized'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400