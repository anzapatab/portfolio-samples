# Extract from HFT Quant Engine
# DuckDB-backed feature store for trading features.
# Provides columnar storage, fast time-series queries,
# point-in-time correctness, and batch insert for 70+ features.

#!/usr/bin/env python3
"""
Feature Store using DuckDB

Responsibilities:
  - Store computed features in columnar format
  - Enable fast time-series queries
  - Support feature versioning
  - Provide point-in-time correctness
"""

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FeatureStore:
    """DuckDB-backed feature store for trading features"""

    def __init__(self, db_path: str = "data/features.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()
        logger.info(f"Feature store initialized: {db_path}")

    def _init_schema(self):
        """Create tables and indexes"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS features_online (
                -- Timestamp and identifiers
                ts TIMESTAMP PRIMARY KEY,
                symbol VARCHAR NOT NULL,
                exchange VARCHAR NOT NULL,

                -- Price features (5)
                price DOUBLE,
                mid_price DOUBLE,
                microprice DOUBLE,
                spread DOUBLE,
                spread_bps DOUBLE,

                -- Returns (8)
                r_1m DOUBLE,   -- 1-minute return
                r_5m DOUBLE,   -- 5-minute return
                r_15m DOUBLE,  -- 15-minute return
                r_log DOUBLE,  -- log return
                r_1h DOUBLE,   -- 1-hour return
                r_4h DOUBLE,   -- 4-hour return
                r_1d DOUBLE,   -- 1-day return
                r_zscore DOUBLE, -- z-score of returns

                -- Volatility (6)
                vol_5m DOUBLE,   -- 5-min rolling std
                vol_15m DOUBLE,  -- 15-min rolling std
                vol_1h DOUBLE,   -- 1-hour rolling std
                vol_4h DOUBLE,   -- 4-hour rolling std
                realized_vol DOUBLE,
                parkinson_vol DOUBLE,  -- High-low volatility

                -- Volume features (6)
                volume DOUBLE,
                dollar_volume DOUBLE,
                volume_ma_1h DOUBLE,
                volume_ratio DOUBLE,    -- current / MA
                vwap DOUBLE,            -- Volume-weighted average price
                volume_imbalance DOUBLE, -- Buy volume - sell volume

                -- Order book features (8)
                book_imbalance DOUBLE,  -- (bid_qty - ask_qty) / total
                bid_ask_spread DOUBLE,
                effective_spread DOUBLE,
                realized_spread DOUBLE,
                price_impact DOUBLE,
                depth_imbalance DOUBLE,
                ofi DOUBLE,             -- Order Flow Imbalance
                trade_flow DOUBLE,

                -- Technical indicators (15)
                rsi_14 DOUBLE,
                rsi_30 DOUBLE,
                macd DOUBLE,
                macd_signal DOUBLE,
                macd_hist DOUBLE,
                bb_upper DOUBLE,
                bb_middle DOUBLE,
                bb_lower DOUBLE,
                bb_width DOUBLE,
                bb_position DOUBLE,     -- Where price is within bands
                atr_14 DOUBLE,          -- Average True Range
                adx_14 DOUBLE,          -- Average Directional Index
                cci_20 DOUBLE,          -- Commodity Channel Index
                stoch_k DOUBLE,         -- Stochastic K
                stoch_d DOUBLE,         -- Stochastic D

                -- Moving averages (6)
                ema_12 DOUBLE,
                ema_26 DOUBLE,
                ema_50 DOUBLE,
                sma_20 DOUBLE,
                sma_50 DOUBLE,
                sma_200 DOUBLE,

                -- Market microstructure (5)
                tick_direction INT,     -- 1 (uptick), -1 (downtick)
                trade_intensity DOUBLE, -- Trades per minute
                quote_intensity DOUBLE, -- Quotes per minute
                effective_tick_size DOUBLE,
                roll_measure DOUBLE,    -- Roll's spread estimator

                -- Cross-asset features (6)
                btc_correlation_1h DOUBLE,
                btc_correlation_4h DOUBLE,
                eth_correlation_1h DOUBLE,
                eth_correlation_4h DOUBLE,
                market_beta DOUBLE,
                sector_momentum DOUBLE,

                -- Sentiment & funding (4)
                funding_rate DOUBLE,
                open_interest DOUBLE,
                long_short_ratio DOUBLE,
                sentiment_score DOUBLE,

                -- Labels for supervised learning (3)
                forward_return_5m DOUBLE,   -- y = price[t+5] / price[t] - 1
                forward_return_15m DOUBLE,
                forward_return_1h DOUBLE
            );

            -- Indexes for fast queries
            CREATE INDEX IF NOT EXISTS idx_ts ON features_online(ts);
            CREATE INDEX IF NOT EXISTS idx_symbol ON features_online(symbol);
            CREATE INDEX IF NOT EXISTS idx_ts_symbol ON features_online(ts, symbol);
        """)

        logger.info("Schema initialized: features_online table ready")

    def insert_batch(self, df: pd.DataFrame):
        """Insert features in batch"""
        try:
            self.conn.execute("INSERT INTO features_online SELECT * FROM df")
            logger.info(f"Inserted {len(df)} rows into feature store")
        except Exception as e:
            logger.error(f"Failed to insert batch: {e}")
            raise

    def get_features(
        self,
        symbol: str,
        start_ts: str,
        end_ts: str,
        columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Retrieve features for training/backtesting

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            start_ts: Start timestamp (ISO format)
            end_ts: End timestamp (ISO format)
            columns: Optional list of columns to fetch

        Returns:
            DataFrame with requested features
        """
        cols = "*" if columns is None else ", ".join(columns)

        query = f"""
            SELECT {cols}
            FROM features_online
            WHERE symbol = ?
              AND ts BETWEEN ? AND ?
            ORDER BY ts
        """

        df = self.conn.execute(query, [symbol, start_ts, end_ts]).df()
        logger.info(f"Retrieved {len(df)} rows for {symbol} ({start_ts} to {end_ts})")
        return df

    def get_latest_features(self, symbol: str, limit: int = 1) -> pd.DataFrame:
        """Get most recent features for online inference"""
        query = f"""
            SELECT *
            FROM features_online
            WHERE symbol = ?
            ORDER BY ts DESC
            LIMIT ?
        """
        return self.conn.execute(query, [symbol, limit]).df()

    def stats(self):
        """Print feature store statistics"""
        result = self.conn.execute("""
            SELECT
                symbol,
                COUNT(*) as row_count,
                MIN(ts) as first_ts,
                MAX(ts) as last_ts,
                COUNT(DISTINCT DATE_TRUNC('day', ts)) as days
            FROM features_online
            GROUP BY symbol
            ORDER BY row_count DESC
        """).df()

        print("\n=== Feature Store Statistics ===")
        print(result.to_string(index=False))
        print()

    def close(self):
        """Close database connection"""
        self.conn.close()
        logger.info("Feature store closed")


if __name__ == "__main__":
    # Test
    fs = FeatureStore("data/test_features.db")
    fs.stats()
    fs.close()
