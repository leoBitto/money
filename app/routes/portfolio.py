# app/routes/portfolio.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime, timedelta
import json

from scripts.database import execute_query
from scripts.portfolio import (get_portfolio_snapshot, get_portfolio_positions, 
                              create_portfolio, add_operation, create_portfolio_tables)

portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route('/')
@login_required
def index():
    """Gestione portfolio con visualizzazione posizioni"""
    portfolio_name = request.args.get('name', 'default')
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        # Portfolio snapshot
        snapshot = get_portfolio_snapshot(date, portfolio_name)
        
        # Posizioni dettagliate
        positions_df = get_portfolio_positions(date, portfolio_name)
        positions_data = positions_df.to_dict('records') if not positions_df.empty else []
        
        # Lista portfolio disponibili
        available_portfolios_query = """
            SELECT DISTINCT portfolio_name FROM portfolio_snapshots 
            ORDER BY portfolio_name
        """
        portfolio_results = execute_query(available_portfolios_query)
        available_portfolios = [row[0] for row in portfolio_results] if portfolio_results else ['default']
        
        # Performance chart data (ultimi 30 giorni)
        chart_start = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        performance_query = """
            SELECT date, total_value, daily_return_pct 
            FROM portfolio_snapshots 
            WHERE portfolio_name = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """
        perf_results = execute_query(performance_query, (portfolio_name, chart_start, date))
        performance_data = [
            {
                'date': row[0].strftime('%Y-%m-%d'),
                'value': float(row[1]),
                'return_pct': float(row[2]) if row[2] else 0
            }
            for row in perf_results
        ] if perf_results else []
        
        return render_template("portfolio/index.html",
                             snapshot=snapshot,
                             positions=positions_data,
                             available_portfolios=available_portfolios,
                             current_portfolio=portfolio_name,
                             current_date=date,
                             performance_data=json.dumps(performance_data))
    
    except Exception as e:
        flash(f'Error loading portfolio: {e}', 'danger')
        return render_template("portfolio/index.html", error=str(e))

@portfolio_bp.route('/create', methods=['POST'])
@login_required
def create_portfolio_route():
    """Crea nuovo portfolio"""
    try:
        name = request.form.get('name', '').strip()
        initial_cash = float(request.form.get('initial_cash', 10000))
        
        if not name:
            flash('Portfolio name is required', 'danger')
            return redirect(url_for('portfolio.index'))
        
        create_portfolio(name, initial_cash)
        flash(f'Portfolio "{name}" created successfully with ${initial_cash:,.2f}', 'success')
        return redirect(url_for('portfolio.index', name=name))
    
    except Exception as e:
        flash(f'Error creating portfolio: {e}', 'danger')
        return redirect(url_for('portfolio.index'))

@portfolio_bp.route('/trade', methods=['POST'])
@login_required
def execute_trade():
    """Esegue un trade manuale"""
    try:
        portfolio_name = request.form.get('portfolio_name', 'default')
        action = request.form.get('action')  # BUY/SELL
        ticker = request.form.get('ticker', '').upper().strip()
        shares = int(request.form.get('shares'))
        price = float(request.form.get('price'))
        date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not all([action, ticker, shares > 0, price > 0]):
            return jsonify({'error': 'All fields are required and must be valid'}), 400
        
        add_operation(portfolio_name, action, ticker, shares, price, date)
        
        return jsonify({
            'success': True, 
            'message': f'{action} {shares} {ticker} @ ${price:.2f}'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400
