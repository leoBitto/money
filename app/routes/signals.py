# app/routes/signals.py
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from datetime import datetime, timedelta

from scripts.database import get_universe_data, get_available_tickers
from scripts.signals import generate_signals_df
from scripts import strategies
from scripts.config import DEFAULT_STRATEGY_PARAMS

signals_bp = Blueprint('signals', __name__)

@signals_bp.route('/')
@login_required
def index():
    """Pagina per generare e visualizzare segnali"""
    try:
        # Strategie disponibili
        strategy_functions = []
        for name in dir(strategies):
            if not name.startswith('_') and callable(getattr(strategies, name)):
                strategy_functions.append(name)
        
        tickers = get_available_tickers()[:20]  # Prime 20 per non sovraccaricare
        
        return render_template("signals/index.html", 
                             strategies=strategy_functions,
                             tickers=tickers,
                             default_params=DEFAULT_STRATEGY_PARAMS)
    
    except Exception as e:
        return render_template("signals/index.html", error=str(e))

@signals_bp.route('/generate', methods=['POST'])
@login_required
def generate_signals():
    """Genera segnali per una strategia specifica"""
    try:
        strategy_name = request.form.get('strategy')
        selected_tickers = request.form.getlist('tickers')
        
        if not strategy_name or not selected_tickers:
            return jsonify({'error': 'Strategy and tickers are required'}), 400
        
        # Carica strategia
        strategy_fn = getattr(strategies, strategy_name)
        
        # Parametri custom (se forniti)
        params = DEFAULT_STRATEGY_PARAMS.get(strategy_name, {}).copy()
        for key, default_value in params.items():
            form_value = request.form.get(f'param_{key}')
            if form_value:
                # Cerca di convertire al tipo corretto
                if isinstance(default_value, int):
                    params[key] = int(form_value)
                elif isinstance(default_value, float):
                    params[key] = float(form_value)
                else:
                    params[key] = form_value
        
        # Carica dati (ultimi 60 giorni)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        df = get_universe_data(start_date=start_date, end_date=end_date, tickers=selected_tickers)
        
        if df.empty:
            return jsonify({'error': 'No data available'}), 400
        
        # Genera segnali
        signals_df = generate_signals_df(strategy_fn, df, **params)
        
        # Distribuzione segnali
        signal_counts = signals_df['signal'].value_counts().to_dict()
        
        return jsonify({
            'signals': signals_df.to_dict('records'),
            'summary': signal_counts,
            'strategy': strategy_name,
            'params_used': params
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400