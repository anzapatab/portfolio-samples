# ETL Pipeline -- Polars & Parallel I/O

Extracts from production data pipelines processing electricity market and financial data across Latin American energy systems.

## Full Project Context

These modules are part of larger systems totaling **89K+ lines of code**, handling daily ingestion of market data from multiple sources (CENACE, CEN, XM, REE). The pipelines run on scheduled jobs processing hundreds of GBs of CSV, Parquet, and Arrow files per week -- feeding downstream optimization models, dashboards, and reporting tools.

## What This Sample Shows

- **Parallel CSV/Parquet ingestion** -- `ProcessPoolExecutor` for CPU-bound year-level conversion, `ThreadPoolExecutor` (up to 64 workers) for I/O-bound file reads
- **Data transformation with Polars** -- 3-10x faster than pandas for CSV/Parquet operations, lazy evaluation with `LazyFrame` for query optimization, streaming collection for memory efficiency
- **Caching strategies** -- Thread-safe in-memory cache with TTL eviction, automatic Excel-to-Parquet on-demand conversion, parallel cache warmup
- **Schema validation & normalization** -- Case-insensitive column matching, automatic type casting, multi-format Arrow file scanning
- **Batch database loading** -- Polars-based ZIP/CSV processing with batch `INSERT OR IGNORE` for high-throughput SQLite ingestion (~10x faster than sequential pandas)

## Structure

```
etl-pipeline/
  extractors/
    csv_to_parquet.py          # Parallel CSV-to-Parquet converter (ProcessPoolExecutor)
    parallel_series_builder.py # Parallel Arrow reader + pivoted DataFrame builder (64 threads)
    parallel_api_scraper.py    # Threaded API scraper with rate limiting and retry logic
  transformers/
    polars_data_loader.py      # High-performance Polars data loading with lazy evaluation
    data_cache.py              # Thread-safe DataFrame cache with TTL + parallel Excel conversion
  loaders/
    parallel_io.py             # Generic parallel CSV loading with per-file kwargs and processors
    batch_loader.py            # Polars ZIP processing + batch SQLite insertion
    arrow_scanner.py           # Parallel Arrow/IPC scanner with schema normalization
```

## Tech

Python | Polars | ThreadPoolExecutor | ProcessPoolExecutor | aiohttp | PyArrow | SQLite
