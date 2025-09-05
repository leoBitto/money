import pandas as pd

def moving_average_crossover(df, short_window=3, long_window=5):
    """
    Moving Average Crossover Strategy.

    Logic explanation:
    This strategy assumes that when the short-term trend (short moving average)
    crosses above the long-term trend (long moving average), the price is
    gaining momentum and it's likely to continue rising. Hence, a buy signal is
    generated. Conversely, when the short-term trend crosses below the long-term
    trend, momentum is weakening and a sell signal is generated.

    Technical explanation:
    - Buy (signal=1) when short moving average > long moving average
    - Sell (signal=-1) when short moving average < long moving average
    - Hold (signal=0) otherwise

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing at least the 'close' column.
    short_window : int
        Number of periods for the short moving average.
    long_window : int
        Number of periods for the long moving average.

    Returns
    -------
    pd.DataFrame
        Original DataFrame plus:
        - 'MA_short': short-term moving average
        - 'MA_long': long-term moving average
        - 'signal': trading signal (1=buy, -1=sell, 0=hold)
    """
    # copy dataframe to avoid modifying original
    df = df.copy()

    # calculate short and long moving averages
    df['MA_short'] = df['close'].rolling(short_window).mean()
    df['MA_long'] = df['close'].rolling(long_window).mean()

    # initialize signal column
    df['signal'] = 0

    # generate buy signal
    df.loc[df['MA_short'] > df['MA_long'], 'signal'] = 1

    # generate sell signal
    df.loc[df['MA_short'] < df['MA_long'], 'signal'] = -1

    return df

def rsi_strategy(df, period=14, overbought=70, oversold=30):
    """
    RSI (Relative Strength Index) Strategy.

    Logic explanation:
    RSI measures the speed and change of price movements. When RSI exceeds
    the overbought threshold, the asset may be overvalued and a sell signal
    is generated. When RSI goes below the oversold threshold, the asset may
    be undervalued and a buy signal is generated.

    Technical explanation:
    - Calculate daily gains and losses
    - Compute average gain/loss over the period
    - Compute RSI = 100 - (100 / (1 + RS))
    - Buy signal (1) if RSI < oversold
    - Sell signal (-1) if RSI > overbought
    - Hold (0) otherwise

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing at least the 'close' column.
    period : int
        Number of periods for RSI calculation.
    overbought : float
        RSI level considered overbought.
    oversold : float
        RSI level considered oversold.

    Returns
    -------
    pd.DataFrame
        Original DataFrame plus:
        - 'RSI': RSI value
        - 'signal': trading signal (1=buy, -1=sell, 0=hold)
    """
    df = df.copy()
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['signal'] = 0
    df.loc[df['RSI'] < oversold, 'signal'] = 1
    df.loc[df['RSI'] > overbought, 'signal'] = -1
    
    return df

def breakout_strategy(df, lookback=20):
    """
    Price Breakout Strategy.

    Logic explanation:
    The strategy identifies new highs/lows over a lookback period. When the
    current close exceeds the highest high in the past 'lookback' days, it
    indicates strong bullish momentum → buy signal. Conversely, if the close
    falls below the lowest low of the lookback period, it signals bearish
    momentum → sell signal.

    Technical explanation:
    - Compute rolling max and min over the lookback window
    - Buy signal (1) if close > rolling max
    - Sell signal (-1) if close < rolling min
    - Hold (0) otherwise

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing at least the 'close' column.
    lookback : int
        Number of periods to look back for highs/lows.

    Returns
    -------
    pd.DataFrame
        Original DataFrame plus:
        - 'rolling_max': highest close in lookback window
        - 'rolling_min': lowest close in lookback window
        - 'signal': trading signal (1=buy, -1=sell, 0=hold)
    """
    df = df.copy()
    df['rolling_max'] = df['close'].rolling(lookback).max()
    df['rolling_min'] = df['close'].rolling(lookback).min()
    
    df['signal'] = 0
    df.loc[df['close'] > df['rolling_max'], 'signal'] = 1
    df.loc[df['close'] < df['rolling_min'], 'signal'] = -1
    
    return df
