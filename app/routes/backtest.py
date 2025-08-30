# app/routes/backtest.py
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required

from scripts.database import get_available_tickers
from scripts import strategies
from scripts.config import DEFAULT_STRATEGY_PARAMS
from scripts.backtest import run_backtest

backtest_bp = Blueprint('backtest', __name__)

@backtest_bp.route('/')
@login_required
def index():
    """Pagina per eseguire backtest"""
    try:
        # Strategie disponibili
        strategy_functions = []
        for name in dir(strategies):
            if not name.startswith('_') and callable(getattr(strategies, name)):
                strategy_functions.append(name)
        
        tickers = get_available_tickers()
        
        return render_template("backtest/index.html",
                             strategies=strategy_functions,
                             tickers=tickers,
                             default_params=DEFAULT_STRATEGY_PARAMS)
    
    except Exception as e:
        return render_template("backtest/index.html", error=str(e))

@backtest_bp.route('/run', methods=['POST'])
@login_required
def run_backtest_route():
    """Esegue backtest di una strategia"""
    try:
        strategy_name = request.form.get('strategy')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        selected_tickers = request.form.getlist('tickers')
        initial_capital = float(request.form.get('initial_capital', 100000))
        
        if not all([strategy_name, start_date, end_date, selected_tickers]):
            return jsonify({'error': 'All fields are required'}), 400
        
        # Carica strategia
        strategy_fn = getattr(strategies, strategy_name)
        
        # Parametri custom
        params = DEFAULT_STRATEGY_PARAMS.get(strategy_name, {}).copy()
        for key, default_value in params.items():
            form_value = request.form.get(f'param_{key}')
            if form_value:
                if isinstance(default_value, int):
                    params[key] = int(form_value)
                elif isinstance(default_value, float):
                    params[key] = float(form_value)
        
        # Esegui backtest
        results = run_backtest(
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
            tickers=selected_tickers,
            initial_capital=initial_capital,
            **params
        )
        
        # Prepara dati per visualizzazione
        portfolio_history = results['portfolio_history'].to_dict('records')
        trades_history = results['trades_history'].to_dict('records')
        
        return jsonify({
            'success': True,
            'results': results['portfolio_metrics'],
            'trade_metrics': results['trade_metrics'],
            'portfolio_history': portfolio_history,
            'trades_history': trades_history,
            'strategy': strategy_name,
            'period': f"{start_date} to {end_date}"
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400
