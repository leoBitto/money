# app/routes/query.py
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required

from scripts.database import execute_query

query_bp = Blueprint('query', __name__)

@query_bp.route('/')
@login_required
def index():
    """SQL Query interface per analisi custom"""
    
    # Preset queries utili
    preset_queries = {
        "Top Performers": """
            SELECT ticker, 
                   MAX(close) as max_price,
                   MIN(close) as min_price,
                   (MAX(close) - MIN(close)) / MIN(close) * 100 as range_pct
            FROM universe 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY ticker 
            ORDER BY range_pct DESC 
            LIMIT 10
        """,
        "Volume Leaders": """
            SELECT ticker, date, volume, close
            FROM universe 
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY volume DESC 
            LIMIT 20
        """,
        "Recent Data Check": """
            SELECT ticker, MAX(date) as last_update, COUNT(*) as total_records
            FROM universe 
            GROUP BY ticker 
            ORDER BY last_update DESC
        """,
        "Portfolio Performance": """
            SELECT date, portfolio_name, total_value, daily_return_pct
            FROM portfolio_snapshots 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY date DESC
        """
    }
    
    return render_template("query/index.html", preset_queries=preset_queries)

@query_bp.route('/execute', methods=['POST'])
@login_required
def execute_query_route():
    """Esegue query SQL e restituisce risultati"""
    try:
        query = request.form.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Empty query'}), 400
        
        # Sicurezza base: solo SELECT
        if not query.upper().startswith('SELECT'):
            return jsonify({'error': 'Only SELECT queries are allowed'}), 400
        
        results = execute_query(query)
        
        if not results:
            return jsonify({'columns': [], 'data': [], 'message': 'No results'})
        
        # Estrai nomi colonne (semplificato)
        columns = [f'col_{i}' for i in range(len(results[0]))]
        
        # Converti risultati in formato JSON-friendly
        data = []
        for row in results:
            row_data = []
            for value in row:
                if hasattr(value, 'strftime'):  # datetime
                    row_data.append(value.strftime('%Y-%m-%d'))
                elif isinstance(value, (int, float)):
                    row_data.append(value)
                else:
                    row_data.append(str(value))
            data.append(row_data)
        
        return jsonify({
            'columns': columns,
            'data': data,
            'row_count': len(data)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400