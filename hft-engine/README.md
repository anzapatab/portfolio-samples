# HFT Quant Engine

Extract from a C++20 high-frequency trading engine with sub-millisecond ML inference via ONNX Runtime. The full system ingests real-time WebSocket market data, computes streaming features, runs LightGBM predictions, and publishes trading signals over ZeroMQ -- all on a latency-optimized hot path.

> **Note:** This is a curated extract for portfolio review. The full project includes live exchange connectivity, order management, risk controls, walk-forward optimization, and a Bronze/Silver data lake pipeline.

## Architecture

```
WebSocket Feed ──> Market Data Normalizer ──> Feature Engine ──> ONNX Inference ──> Signal Publisher
     (L1 + trades)        (SPSC ring buffers)     (streaming EMA,       (LightGBM)       (ZeroMQ PUB/SUB)
                                                   MACD, RSI, OFI,
                                                   microprice)
```

## What's Here

### C++ Core (`cpp/` and `include/`)

| File | Description |
|---|---|
| `backtest_engine.cpp` | 600+ line backtesting engine with simulated exchange (order matching, maker/taker fees, slippage modeling), Parquet data loading via Apache Arrow, FIFO trade detection, Sharpe/drawdown/profit-factor metrics |
| `features_online.cpp` | Streaming feature computation from tick-level data: EMA(12,26), MACD, RSI(14), Order Flow Imbalance (OFI), microprice, spread -- all via lock-free SPSC ring buffers |
| `inference_engine.cpp` | ONNX Runtime wrapper for single-event inference on the hot path; handles both tensor and seq(map) probability outputs from LightGBM classifiers |
| `include/bqe/ring_buffer.hpp` | Cache-line aligned (`alignas(64)`) lock-free SPSC ring buffer with acquire/release memory ordering |
| `include/bqe/ml_signal.hpp` | ML signal generator: confidence thresholds, edge filtering, cooldown logic, spread checks, Kelly-inspired position sizing |
| `include/bqe/signal_publisher.hpp` | ZeroMQ PUB/SUB broadcaster with topic-based routing (`SIGNAL.BTCUSDT.BUY`) |
| `include/bqe/simd_utils.hpp` | AVX2 SIMD intrinsics: vectorized EMA, stddev, dot product, fast polynomial log approximation (~5x vs `std::log`) |
| `include/bqe/types.hpp` | Core POD types: nanosecond timestamps, `TradeFrame`, `BookL1`, `FeaturesOnline` |

### Python ML Pipeline (`python/`)

| File | Description |
|---|---|
| `ml_training_optuna.py` | LightGBM training with Optuna TPE hyperparameter search, time-series cross-validation, direction accuracy evaluation |
| `feature_engineering.py` | 70+ feature pipeline: multi-horizon returns, Parkinson volatility, VWAP, RSI, MACD, Bollinger Bands, ADX, CCI, Stochastic -- with TA-Lib fast path |
| `feature_store.py` | DuckDB-backed feature store with 70-column schema, point-in-time queries, batch insert, and online inference retrieval |

## Technology Stack

| Layer | Technology |
|---|---|
| Language | C++20, Python 3.12 |
| Build | CMake 3.16+, ccache, lld |
| ML Inference | ONNX Runtime (single-threaded, `ORT_ENABLE_ALL` graph optimization) |
| ML Training | LightGBM, Optuna (TPE sampler), scikit-learn |
| Data | Apache Arrow / Parquet (columnar), DuckDB (feature store) |
| Messaging | ZeroMQ (PUB/SUB for signal distribution) |
| Serialization | Protocol Buffers (real-time features) |
| Networking | Boost.Beast (WebSocket), libcurl (REST) |
| Logging | spdlog |
| SIMD | AVX2 / FMA intrinsics for hot-path math |

## Performance Characteristics

- **Inference latency:** <1ms per prediction (ONNX Runtime, single-threaded CPU)
- **Feature computation:** Lock-free SPSC rings, zero-copy between producer/consumer threads
- **Memory ordering:** `std::memory_order_acquire`/`release` on ring buffer head/tail (no mutexes)
- **Cache optimization:** `alignas(64)` on atomic counters to prevent false sharing
- **SIMD hot path:** AVX2 vectorized EMA processes 4 doubles per instruction cycle
- **Build optimization:** `-O3 -march=native -fno-omit-frame-pointer` on the silver core library
