# Extract from HFT Quant Engine
# Feature engineering pipeline: transforms raw OHLCV data into 70+
# trading features including returns, volatility, volume profiles,
# technical indicators (RSI, MACD, Bollinger Bands, ADX, CCI, Stochastic),
# and forward return labels for supervised learning.

#!/usr/bin/env python3
"""
Feature Engineering Pipeline

Transforms raw OHLCV data into 70+ trading features
"""

import pandas as pd
import numpy as np
from typing import Optional
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import talib, fallback to manual implementations if not available
try:
    import talib
    HAS_TALIB = True
    logger.info("TA-Lib available, using optimized implementations")
except ImportError:
    HAS_TALIB = False
    logger.warning("TA-Lib not available, using manual implementations (slower)")


class FeatureEngineer:
    """Compute trading features from OHLCV data"""

    def __init__(self):
        self.feature_count = 0

    def compute_all_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Main entry point: compute all features

        Args:
            df: OHLCV dataframe with columns:
                - timestamp, open, high, low, close, volume

        Returns:
            DataFrame with 70+ features
        """
        df = df.copy()

        # Ensure sorted by time
        df = df.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"Computing features for {len(df)} rows...")

        # Compute feature groups
        df = self._price_features(df)
        df = self._return_features(df)
        df = self._volatility_features(df)
        df = self._volume_features(df)
        df = self._technical_indicators(df)
        df = self._moving_averages(df)
        df = self._labels(df)

        # Fill placeholder features with 0
        self._fill_placeholder_features(df)

        self.feature_count = len([c for c in df.columns if c not in
                                  ['timestamp', 'open', 'high', 'low', 'close', 'volume']])

        logger.info(f"Computed {self.feature_count} features")

        return df

    def _price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Basic price-derived features"""
        df['price'] = df['close']
        df['mid_price'] = (df['high'] + df['low']) / 2
        df['spread'] = df['high'] - df['low']
        df['spread_bps'] = (df['spread'] / df['close']) * 10000  # Basis points

        # Microprice (simple version without order book)
        df['microprice'] = df['close']  # Placeholder

        return df

    def _return_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return calculations at multiple horizons"""
        # Simple returns
        df['r_1m'] = df['close'].pct_change(periods=1)
        df['r_5m'] = df['close'].pct_change(periods=5)
        df['r_15m'] = df['close'].pct_change(periods=15)
        df['r_1h'] = df['close'].pct_change(periods=60)
        df['r_4h'] = df['close'].pct_change(periods=240)
        df['r_1d'] = df['close'].pct_change(periods=1440)

        # Log returns (more stable for modeling)
        df['r_log'] = np.log(df['close'] / df['close'].shift(1))

        # Z-score of returns (mean reversion signal)
        rolling_mean = df['r_1m'].rolling(window=60).mean()
        rolling_std = df['r_1m'].rolling(window=60).std()
        df['r_zscore'] = (df['r_1m'] - rolling_mean) / (rolling_std + 1e-8)

        return df

    def _volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Volatility measures"""
        # Rolling standard deviation of returns
        df['vol_5m'] = df['r_1m'].rolling(window=5).std()
        df['vol_15m'] = df['r_1m'].rolling(window=15).std()
        df['vol_1h'] = df['r_1m'].rolling(window=60).std()
        df['vol_4h'] = df['r_1m'].rolling(window=240).std()

        # Realized volatility (sum of squared returns)
        df['realized_vol'] = np.sqrt((df['r_1m'] ** 2).rolling(window=60).sum())

        # Parkinson volatility (uses high-low range)
        df['parkinson_vol'] = np.sqrt(
            (1 / (4 * np.log(2))) *
            ((np.log(df['high'] / df['low'])) ** 2).rolling(window=20).mean()
        )

        return df

    def _volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Volume-based features"""
        df['volume'] = df['volume']
        df['dollar_volume'] = df['close'] * df['volume']

        # Volume moving average
        df['volume_ma_1h'] = df['volume'].rolling(window=60).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_ma_1h'] + 1e-8)

        # VWAP (Volume-Weighted Average Price)
        df['vwap'] = (
            (df['close'] * df['volume']).rolling(window=60).sum() /
            df['volume'].rolling(window=60).sum()
        )

        # Volume imbalance (placeholder - needs tick data)
        df['volume_imbalance'] = 0.0

        return df

    def _technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Technical indicators using TA-Lib or manual implementations"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values

        if HAS_TALIB:
            # RSI (Relative Strength Index)
            df['rsi_14'] = talib.RSI(close, timeperiod=14)
            df['rsi_30'] = talib.RSI(close, timeperiod=30)

            # MACD
            macd, macd_signal, macd_hist = talib.MACD(
                close,
                fastperiod=12,
                slowperiod=26,
                signalperiod=9
            )
            df['macd'] = macd
            df['macd_signal'] = macd_signal
            df['macd_hist'] = macd_hist

            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = talib.BBANDS(
                close,
                timeperiod=20,
                nbdevup=2,
                nbdevdn=2
            )
            df['bb_upper'] = bb_upper
            df['bb_middle'] = bb_middle
            df['bb_lower'] = bb_lower
            df['bb_width'] = (bb_upper - bb_lower) / (bb_middle + 1e-8)
            df['bb_position'] = (close - bb_lower) / (bb_upper - bb_lower + 1e-8)

            # ATR (Average True Range)
            df['atr_14'] = talib.ATR(high, low, close, timeperiod=14)

            # ADX (Average Directional Index)
            df['adx_14'] = talib.ADX(high, low, close, timeperiod=14)

            # CCI (Commodity Channel Index)
            df['cci_20'] = talib.CCI(high, low, close, timeperiod=20)

            # Stochastic Oscillator
            stoch_k, stoch_d = talib.STOCH(
                high, low, close,
                fastk_period=14,
                slowk_period=3,
                slowd_period=3
            )
            df['stoch_k'] = stoch_k
            df['stoch_d'] = stoch_d

        else:
            # Manual implementations (simplified)
            df['rsi_14'] = self._compute_rsi(df['close'], 14)
            df['rsi_30'] = self._compute_rsi(df['close'], 30)

            macd, macd_signal = self._compute_macd(df['close'])
            df['macd'] = macd
            df['macd_signal'] = macd_signal
            df['macd_hist'] = macd - macd_signal

            # Bollinger Bands
            bb_ma = df['close'].rolling(20).mean()
            bb_std = df['close'].rolling(20).std()
            df['bb_upper'] = bb_ma + 2 * bb_std
            df['bb_middle'] = bb_ma
            df['bb_lower'] = bb_ma - 2 * bb_std
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / (bb_ma + 1e-8)
            df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-8)

            # Placeholders for complex indicators
            df['atr_14'] = df['spread'].rolling(14).mean()
            df['adx_14'] = 50.0  # Neutral
            df['cci_20'] = 0.0
            df['stoch_k'] = 50.0
            df['stoch_d'] = 50.0

        return df

    def _moving_averages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Moving average features"""
        close = df['close'].values

        if HAS_TALIB:
            # Exponential Moving Averages
            df['ema_12'] = talib.EMA(close, timeperiod=12)
            df['ema_26'] = talib.EMA(close, timeperiod=26)
            df['ema_50'] = talib.EMA(close, timeperiod=50)

            # Simple Moving Averages
            df['sma_20'] = talib.SMA(close, timeperiod=20)
            df['sma_50'] = talib.SMA(close, timeperiod=50)
            df['sma_200'] = talib.SMA(close, timeperiod=200)
        else:
            # Manual EMA
            df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
            df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

            # Manual SMA
            df['sma_20'] = df['close'].rolling(20).mean()
            df['sma_50'] = df['close'].rolling(50).mean()
            df['sma_200'] = df['close'].rolling(200).mean()

        return df

    def _labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Forward returns for supervised learning"""
        # Forward returns (what we want to predict)
        df['forward_return_5m'] = df['close'].shift(-5) / df['close'] - 1
        df['forward_return_15m'] = df['close'].shift(-15) / df['close'] - 1
        df['forward_return_1h'] = df['close'].shift(-60) / df['close'] - 1

        return df

    def _fill_placeholder_features(self, df: pd.DataFrame):
        """Fill features that need order book data with placeholders"""
        placeholder_features = [
            'book_imbalance', 'bid_ask_spread', 'effective_spread',
            'realized_spread', 'price_impact', 'depth_imbalance',
            'ofi', 'trade_flow', 'tick_direction', 'trade_intensity',
            'quote_intensity', 'effective_tick_size', 'roll_measure',
            'btc_correlation_1h', 'btc_correlation_4h',
            'eth_correlation_1h', 'eth_correlation_4h',
            'market_beta', 'sector_momentum',
            'funding_rate', 'open_interest', 'long_short_ratio', 'sentiment_score'
        ]

        for feature in placeholder_features:
            if feature not in df.columns:
                df[feature] = 0.0

    def _compute_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Manual RSI calculation"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / (loss + 1e-8)
        return 100 - (100 / (1 + rs))

    def _compute_macd(self, prices: pd.Series):
        """Manual MACD calculation"""
        ema12 = prices.ewm(span=12, adjust=False).mean()
        ema26 = prices.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal
