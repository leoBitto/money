# scripts/reports.py
"""
Modulo: reports (Refactored with RiskManager)
============================================

Generazione di report settimanali completi del portfolio su Google Sheets.
Integrato con RiskManager per segnali validati e metriche avanzate.

STRUTTURA GOOGLE SHEET:
1. Portfolio_Overview: Metriche aggregate del portfolio
2. Active_Positions: Dettaglio posizioni correnti  
3. Strategy_[Nome]: Segnali per ogni strategia con validazione risk manager
4. Execution_Summary: Dashboard riassuntivo per decisioni weekend

FLUSSO:
- Carica portfolio corrente
- Genera segnali da tutte le strategie
- Valida segnali con risk manager
- Scrive fogli Google Sheets organizzati

CONFIG UTILIZZATI:
- TEST_SHEET_ID: ID del Google Sheet
- DEFAULT_STRATEGY_PARAMS: Parametri per ogni strategia
- Portfolio "demo" come default
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  
from typing import Dict, List, Any
from gspread_dataframe import set_with_dataframe

from . import config
from .google_services import get_gsheet_client
from .risk_manager import RiskManager
from .portfolio import Portfolio



logger = logging.getLogger(__name__)


def _previous_business_day(tz_name: str = "Europe/Rome") -> str:
    today = datetime.now(ZoneInfo(tz_name)).date()
    d = today - timedelta(days=1)
    # 5=Sabato, 6=Domenica
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime('%Y-%m-%d')

# ================================
# MAIN REPORT GENERATION
# ================================

def generate_weekly_report(portfolio_name: str = "demo", 
                          date: str = None) -> Dict[str, Any]:
    """
    Genera report settimanale completo del portfolio.
    
    Args:
        portfolio_name: Nome del portfolio (default: "demo")
        date: Data per il report (default: oggi)
        
    Returns:
        Dict con summary della generazione
    """
    report_date = date or _previous_business_day()
    logger.info(f"🚀 Inizio generazione report settimanale per {portfolio_name} @ {report_date}")
    
    try:
        # Setup Google Sheets client
        client = get_gsheet_client()
        spreadsheet = client.open_by_key(config.TEST_SHEET_ID)
        logger.info("✅ Collegamento Google Sheets stabilito")
        
        # Setup RiskManager
        risk_manager = RiskManager(portfolio_name, report_date)
        logger.info(f"✅ Portfolio '{portfolio_name}' caricato")
        
        # Genera tutti i componenti del report
        report_data = _generate_all_report_data(risk_manager)
        
        # Scrive i fogli Google Sheets
        sheets_written = _write_google_sheets(spreadsheet, report_data, report_date)
        
        # Summary finale
        result = {
            'success': True,
            'portfolio_name': portfolio_name,
            'date': report_date,
            'sheets_written': sheets_written,
            'portfolio_summary': report_data['portfolio_overview'],
            'total_signals': sum(len(signals) for signals in report_data['strategy_signals'].values()),
            'approved_orders': sum(len([o for o in orders if o.get('approved', False)]) 
                                 for orders in report_data['strategy_orders'].values())
        }
        
        logger.info("🎉 Report settimanale generato con successo!")
        _log_final_summary(result)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Errore nella generazione del report: {e}")
        return {'success': False, 'error': str(e)}


def _generate_all_report_data(risk_manager: RiskManager) -> Dict[str, Any]:
    """
    Genera tutti i dati necessari per il report.
    
    Args:
        risk_manager: RiskManager configurato
        
    Returns:
        Dict con tutti i dati del report
    """
    logger.info("📊 Generazione dati del report...")
    
    # 1. Portfolio Overview
    portfolio_overview = _generate_portfolio_overview(risk_manager)
    
    # 2. Active Positions  
    active_positions = _generate_active_positions(risk_manager)
    
    # 3. Strategy Signals & Orders
    strategy_names = ['moving_average_crossover', 'rsi_strategy', 'breakout_strategy']
    strategy_signals = {}
    strategy_orders = {}
    
    for strategy_name in strategy_names:
        logger.info(f"🔄 Processando strategia: {strategy_name}")
        
        # Genera segnali
        signals_df = risk_manager.generate_signals(strategy_name)
        strategy_signals[strategy_name] = signals_df
        
        # Valida segnali
        if not signals_df.empty:
            validated_orders = risk_manager.validate_signals(signals_df)
            strategy_orders[strategy_name] = validated_orders
        else:
            strategy_orders[strategy_name] = []
    
    # 4. Execution Summary
    execution_summary = _generate_execution_summary(strategy_signals, strategy_orders, risk_manager)
    
    return {
        'portfolio_overview': portfolio_overview,
        'active_positions': active_positions,
        'strategy_signals': strategy_signals,
        'strategy_orders': strategy_orders,
        'execution_summary': execution_summary
    }


# ================================
# DATA GENERATION FUNCTIONS
# ================================

def _generate_portfolio_overview(risk_manager: RiskManager) -> Dict[str, Any]:
    """Genera metriche overview del portfolio."""
    portfolio = risk_manager.portfolio
    
    overview = {
        'Date': risk_manager.date,
        'Portfolio': portfolio.name,
        'Total_Value': round(portfolio.get_total_value(), 2),
        'Cash_Balance': round(portfolio.get_cash_balance(), 2),
        'Positions_Count': portfolio.get_positions_count(),
        'Cash_Utilization%': round(portfolio.get_cash_utilization(), 1),
        'Largest_Position%': round(portfolio.get_largest_position_pct(), 1),
        'Total_Risk%': round(portfolio.get_total_risk_pct(), 1),
    }
    
    # Performance metrics (possono essere None)
    metrics = {
        'Daily_Return%': portfolio.get_total_return_pct(start_date=None),
        'Current_Drawdown%': portfolio.get_current_drawdown(),
        'Max_Drawdown%': portfolio.get_max_drawdown(),
        'Volatility%': portfolio.get_portfolio_volatility(),
        'Sharpe_Ratio': portfolio.get_sharpe_ratio(),
        'Win_Rate%': portfolio.get_win_rate()
    }
    
    # Aggiungi metriche con handling per None
    for key, value in metrics.items():
        overview[key] = round(value, 2) if value is not None else 0.0
    
    return overview


def _generate_active_positions(risk_manager: RiskManager) -> pd.DataFrame:
    """Genera DataFrame delle posizioni attive."""
    portfolio = risk_manager.portfolio
    positions_data = []
    
    for ticker, position in portfolio._positions.items():
        if position.shares > 0:  # Solo posizioni attive
            total_value = portfolio.get_total_value()
            
            pos_data = {
                'Date': risk_manager.date,
                'Portfolio': portfolio.name,
                'Ticker': ticker,
                'Shares': position.shares,
                'Avg_Cost': round(position.avg_cost, 2),
                'Current_Price': round(position.current_price, 2),
                'Current_Value': round(position.get_current_value(), 2),
                'PnL%': round(position.get_unrealized_pnl_pct(), 2),
                'PnL_Amount': round(position.get_unrealized_pnl(), 2),
                'Weight%': round(position.get_position_weight(total_value), 1),
                'Stop_Loss': round(position.stop_loss, 2) if position.stop_loss else None,
                'First_Target': round(position.first_target, 2) if position.first_target else None,
                'Days_Held': position.get_days_held(),
                'Capital_At_Risk': round(position.get_capital_at_risk(), 2)
            }
            positions_data.append(pos_data)
    
    return pd.DataFrame(positions_data)


def _generate_execution_summary(strategy_signals: Dict[str, pd.DataFrame], 
                               strategy_orders: Dict[str, List], 
                               risk_manager: RiskManager) -> Dict[str, Any]:
    """Genera summary per decisioni di esecuzione."""
    portfolio = risk_manager.portfolio
    
    # Conta segnali per strategia
    signal_counts = {}
    for strategy_name, signals_df in strategy_signals.items():
        if not signals_df.empty:
            counts = signals_df['signal'].value_counts().to_dict()
            signal_counts[strategy_name] = {
                'BUY': counts.get('BUY', 0),
                'SELL': counts.get('SELL', 0),
                'HOLD': counts.get('HOLD', 0)
            }
        else:
            signal_counts[strategy_name] = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
    
    # Conta ordini validati
    approved_orders = []
    rejected_orders = []
    total_buy_cost = 0
    
    for strategy_name, orders in strategy_orders.items():
        for order in orders:
            if order.get('approved', False):
                approved_orders.append(order)
                if order['action'] == 'BUY':
                    total_buy_cost += order.get('cost', 0)
            else:
                rejected_orders.append(order)
    
    # Capital allocation
    available_cash = portfolio.get_available_cash()
    cash_after_trades = available_cash - total_buy_cost
    
    return {
        'date': risk_manager.date,
        'portfolio_name': portfolio.name,
        'signal_counts': signal_counts,
        'approved_orders_count': len(approved_orders),
        'rejected_orders_count': len(rejected_orders),
        'total_buy_cost': round(total_buy_cost, 2),
        'available_cash': round(available_cash, 2),
        'cash_after_trades': round(cash_after_trades, 2),
        'current_positions': portfolio.get_positions_count(),
        'max_positions': risk_manager.max_positions,
        'available_slots': risk_manager.max_positions - portfolio.get_positions_count(),
        'portfolio_risk_pct': round(portfolio.get_total_risk_pct(), 1)
    }


# ================================
# GOOGLE SHEETS WRITING
# ================================

def _write_google_sheets(spreadsheet, report_data: Dict[str, Any], date: str) -> List[str]:
    """Scrive tutti i fogli Google Sheets."""
    sheets_written = []
    
    # 1. Portfolio Overview
    try:
        overview_df = pd.DataFrame([report_data['portfolio_overview']])
        _write_or_append_sheet(spreadsheet, "Portfolio_Overview", overview_df)
        sheets_written.append("Portfolio_Overview")
        logger.info("✅ Portfolio_Overview scritto")
    except Exception as e:
        logger.error(f"❌ Errore Portfolio_Overview: {e}")
    
    # 2. Active Positions
    try:
        positions_df = report_data['active_positions']
        if not positions_df.empty:
            _write_or_append_sheet(spreadsheet, "Active_Positions", positions_df)
            sheets_written.append("Active_Positions")
            logger.info(f"✅ Active_Positions scritto ({len(positions_df)} posizioni)")
        else:
            logger.info("⚠️ Nessuna posizione attiva da scrivere")
    except Exception as e:
        logger.error(f"❌ Errore Active_Positions: {e}")
    
    # 3. Strategy Sheets
    for strategy_name in report_data['strategy_signals']:
        try:
            strategy_df = _prepare_strategy_sheet(
                strategy_name, 
                report_data['strategy_signals'][strategy_name],
                report_data['strategy_orders'][strategy_name],
                date
            )
            
            if not strategy_df.empty:
                sheet_name = f"Strategy_{strategy_name.replace('_', '')[:15]}"  # Limite lunghezza
                _write_or_replace_sheet(spreadsheet, sheet_name, strategy_df)
                sheets_written.append(sheet_name)
                logger.info(f"✅ {sheet_name} scritto ({len(strategy_df)} segnali)")
            else:
                logger.info(f"⚠️ Nessun segnale per {strategy_name}")
                
        except Exception as e:
            logger.error(f"❌ Errore strategia {strategy_name}: {e}")
    
    # 4. Execution Summary
    try:
        summary_df = _prepare_execution_summary_sheet(report_data['execution_summary'])
        _write_or_replace_sheet(spreadsheet, "Execution_Summary", summary_df)
        sheets_written.append("Execution_Summary")
        logger.info("✅ Execution_Summary scritto")
    except Exception as e:
        logger.error(f"❌ Errore Execution_Summary: {e}")
    
    return sheets_written


def _prepare_strategy_sheet(strategy_name: str, signals_df: pd.DataFrame, 
                           orders: List[Dict], date: str) -> pd.DataFrame:
    """Prepara DataFrame per foglio strategia con segnali + validazione."""
    if signals_df.empty:
        return pd.DataFrame()
    
    # Crea dict per lookup veloce degli ordini validati
    orders_lookup = {order['ticker']: order for order in orders}
    
    strategy_data = []
    for _, signal in signals_df.iterrows():
        ticker = signal['ticker']
        order = orders_lookup.get(ticker, {})
        
        row = {
            'Date': date,
            'Ticker': ticker,
            'Signal': signal['signal'],
            'Price': round(signal['price'], 2),
            'ATR': round(signal['atr'], 2),
            'Volume': int(signal.get('volume', 0)),
            'Approved': 'YES' if order.get('approved', False) else 'NO',
            'Shares': order.get('shares', 0) if order.get('approved') else 0,
            'Cost': round(order.get('cost', 0), 2) if order.get('approved') else 0,
            'Weight%': round(order.get('position_weight_pct', 0), 1) if order.get('approved') else 0,
            'Stop_Loss': round(order.get('targets', {}).get('stop_loss', 0), 2) if order.get('approved') else 0,
            'Target': round(order.get('targets', {}).get('first_target', 0), 2) if order.get('approved') else 0
        }
        strategy_data.append(row)
    
    return pd.DataFrame(strategy_data)


def _prepare_execution_summary_sheet(summary: Dict[str, Any]) -> pd.DataFrame:
    """Prepara DataFrame per foglio Execution Summary."""
    # Flatten signal counts
    summary_rows = []
    
    # Header row con info generale
    header_row = {
        'Metric': 'PORTFOLIO_INFO',
        'Value': f"{summary['portfolio_name']} @ {summary['date']}",
        'Details': f"Available Cash: €{summary['available_cash']:,.2f}"
    }
    summary_rows.append(header_row)
    
    # Risk info
    risk_row = {
        'Metric': 'RISK_STATUS',
        'Value': f"{summary['portfolio_risk_pct']}%",
        'Details': f"Positions: {summary['current_positions']}/{summary['current_positions'] + summary['available_slots']}"
    }
    summary_rows.append(risk_row)
    
    # Signal counts per strategia
    for strategy_name, counts in summary['signal_counts'].items():
        strategy_row = {
            'Metric': f"SIGNALS_{strategy_name.upper()}",
            'Value': f"B:{counts['BUY']} S:{counts['SELL']} H:{counts['HOLD']}",
            'Details': f"Total: {sum(counts.values())}"
        }
        summary_rows.append(strategy_row)
    
    # Orders summary
    orders_row = {
        'Metric': 'ORDERS_SUMMARY',
        'Value': f"Approved: {summary['approved_orders_count']}, Rejected: {summary['rejected_orders_count']}",
        'Details': f"Total Cost: €{summary['total_buy_cost']:,.2f}"
    }
    summary_rows.append(orders_row)
    
    # Cash after trades
    cash_row = {
        'Metric': 'CASH_AFTER_TRADES',
        'Value': f"€{summary['cash_after_trades']:,.2f}",
        'Details': f"Utilization: {((summary['total_buy_cost'] / summary['available_cash']) * 100) if summary['available_cash'] > 0 else 0:.1f}%"
    }
    summary_rows.append(cash_row)
    
    return pd.DataFrame(summary_rows)


def _write_or_append_sheet(spreadsheet, sheet_name: str, df: pd.DataFrame):
    """Scrive DataFrame appendendo a foglio esistente o creandone uno nuovo."""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        # Appendi i dati (mantieni storico)
        existing_data = worksheet.get_all_values()
        if existing_data:
            # Trova prossima riga vuota
            next_row = len(existing_data) + 1
            # Scrivi solo i dati (senza header)
            values = df.values.tolist()
            if values:
                worksheet.append_rows(values)
        else:
            # Primo inserimento con header
            set_with_dataframe(worksheet, df, include_index=False)
    except:
        # Crea nuovo foglio
        rows_needed = len(df) + 10
        cols_needed = len(df.columns) + 2
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name, 
            rows=str(rows_needed),
            cols=str(cols_needed)
        )
        set_with_dataframe(worksheet, df, include_index=False)


def _write_or_replace_sheet(spreadsheet, sheet_name: str, df: pd.DataFrame):
    """Scrive DataFrame sostituendo contenuto foglio (per dati che cambiano)."""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
    except:
        # Crea nuovo foglio
        rows_needed = len(df) + 10
        cols_needed = len(df.columns) + 2
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=str(rows_needed), 
            cols=str(cols_needed)
        )
    
    set_with_dataframe(worksheet, df, include_index=False)


# ================================
# UTILITIES
# ================================

def _log_final_summary(result: Dict[str, Any]):
    """Log summary finale del report."""
    logger.info("📊 REPORT SUMMARY:")
    logger.info(f"   Portfolio: {result['portfolio_name']}")
    logger.info(f"   Date: {result['date']}")
    logger.info(f"   Sheets written: {len(result['sheets_written'])}")
    logger.info(f"   Total signals: {result['total_signals']}")
    logger.info(f"   Approved orders: {result['approved_orders']}")
    
    portfolio_info = result['portfolio_summary']
    logger.info(f"   Portfolio value: €{portfolio_info['Total_Value']:,.2f}")
    logger.info(f"   Cash available: €{portfolio_info['Cash_Balance']:,.2f}")
    logger.info(f"   Active positions: {portfolio_info['Positions_Count']}")


