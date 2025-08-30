# app/routes/main.py
from flask import Blueprint, render_template
from flask_login import login_required
from datetime import datetime, timedelta
import json

from scripts.database import get_universe_data, get_available_tickers, execute_query
from scripts.portfolio import get_portfolio_snapshot

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    """Dashboard principale"""
    try:
        # Ultimi 60 giorni di dati
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        
        # Top 10 tickers per volume
        tickers = get_available_tickers()[:10] if get_available_tickers() else []
        
        market_data = []
        if tickers:
            df = get_universe_data(start_date=start_date, end_date=end_date, tickers=tickers)
            
            # Calcola performance ultimo giorno per ogni ticker
            for ticker in tickers:
                ticker_data = df[df['ticker'] == ticker].sort_values('date')
                if len(ticker_data) >= 2:
                    latest = ticker_data.iloc[-1]
                    previous = ticker_data.iloc[-2]
                    change_pct = ((latest['Close'] - previous['Close']) / previous['Close']) * 100
                    
                    market_data.append({
                        'ticker': ticker,
                        'price': latest['Close'],
                        'change_pct': change_pct,
                        'volume': latest['Volume'],
                        'date': latest['date'].strftime('%Y-%m-%d')
                    })
        
        # Portfolio summary (default portfolio)
        portfolio_summary = get_portfolio_snapshot(end_date, "default")
        
        # Chart data per market overview
        chart_data = []
        if tickers and not df.empty:
            # Prendi primo ticker per chart esempio
            first_ticker_data = df[df['ticker'] == tickers[0]].sort_values('date')
            chart_data = [
                {
                    'date': row['date'].strftime('%Y-%m-%d'),
                    'price': row['Close']
                }
                for _, row in first_ticker_data.iterrows()
            ]
        
        return render_template("dashboard/index.html", 
                             market_data=market_data,
                             portfolio_summary=portfolio_summary,
                             chart_data=json.dumps(chart_data),
                             tickers_count=len(tickers))
    
    except Exception as e:
        return render_template("dashboard/index.html", error=str(e))

@main_bp.route('/health')
def health_check():
    """Health check per monitoring"""
    try:
        # Test connessione DB
        result = execute_query("SELECT 1")
        db_status = "OK" if result else "ERROR"
        
        # Test dati recenti
        recent_data = execute_query("SELECT MAX(date) FROM universe")
        last_data_date = recent_data[0][0] if recent_data and recent_data[0][0] else None
        
        return {
            'status': 'healthy',
            'database': db_status,
            'last_data_date': last_data_date.strftime('%Y-%m-%d') if last_data_date else None,
            'timestamp': datetime.now().isoformat()
        }
    
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, 500