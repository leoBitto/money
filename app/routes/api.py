# app/routes/api.py
from flask import Blueprint, jsonify, request
from flask_login import login_required
from datetime import datetime, timedelta

from scripts.database import get_universe_data, get_available_tickers

api_bp = Blueprint('api', __name__)

@api_bp.route('/ticker/<ticker>/chart')
@login_required
def ticker_chart_data(ticker):
    """API per dati chart di un singolo ticker"""
    try:
        days = int(request.args.get('days', 30))
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        df = get_universe_data(start_date=start_date, end_date=end_date, tickers=[ticker])
        
        if df.empty:
            return jsonify({'error': f'No data for {ticker}'}), 404
        
        chart_data = [
            {
                'date': row['date'].strftime('%Y-%m-%d'),
                'open': row['Open'],
                'high': row['High'],
                'low': row['Low'],
                'close': row['Close'],
                'volume': row['Volume']
            }
            for _, row in df.iterrows()
        ]
        
        return jsonify({'data': chart_data, 'ticker': ticker})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/tickers/search')
@login_required
def search_tickers():
    """API per ricerca tickers"""
    query = request.args.get('q', '').upper()
    all_tickers = get_available_tickers()
    
    if query:
        filtered = [t for t in all_tickers if query in t]
    else:
        filtered = all_tickers[:20]  # Prime 20
    
    return jsonify({'tickers': filtered})