"""High-performance data loading utilities using Polars.

This module provides fast CSV reading using Polars, which is 3-10x faster than pandas
for typical operations. It maintains compatibility with the existing pandas-based code
by providing conversion methods when needed.

Features:
- Fast CSV reading with Polars (3-10x faster than pandas)
- Lazy evaluation with LazyFrame for large datasets
- Automatic encoding detection
- Memory-efficient processing through streaming
- Smart eager/lazy selection based on file size

Source: Production data loader for energy market optimization pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    import pandas as pd

# Default encodings for CSV files
DEFAULT_CSV_ENCODING = "utf-8"
FALLBACK_CSV_ENCODING = "cp1252"

# Threshold for using lazy loading (50 MB)
LAZY_LOADING_THRESHOLD_BYTES = 50 * 1024 * 1024


def read_csv_polars(
    path: Path,
    encoding: str | None = None,
    **kwargs,
) -> pl.DataFrame:
    """
    Read a CSV file using Polars with robust encoding handling.

    Polars is 3-10x faster than pandas for CSV reading operations.

    Parameters
    ----------
    path : Path
        Path to the CSV file
    encoding : str, optional
        Encoding to use. If None, uses DEFAULT_CSV_ENCODING
    **kwargs
        Additional arguments passed to pl.read_csv()

    Returns
    -------
    pl.DataFrame
        Polars DataFrame with the data

    Raises
    ------
    FileNotFoundError
        If the file doesn't exist
    ValueError
        If the file can't be read with any encoding
    """
    if encoding is None:
        encoding = DEFAULT_CSV_ENCODING

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Try with primary encoding
    try:
        return pl.read_csv(path, encoding=encoding, **kwargs)
    except Exception as e:
        # Try fallback encoding
        try:
            return pl.read_csv(path, encoding=FALLBACK_CSV_ENCODING, **kwargs)
        except Exception as e2:
            raise ValueError(
                f"Could not read {path} with any encoding. Final error: {e2}"
            ) from e2


def read_csv_to_pandas(
    path: Path,
    encoding: str | None = None,
    **kwargs,
) -> "pd.DataFrame":
    """
    Read a CSV file using Polars and convert to pandas DataFrame.

    This provides the speed of Polars for reading while maintaining
    compatibility with existing pandas-based code.
    """
    df_polars = read_csv_polars(path, encoding=encoding, **kwargs)
    return df_polars.to_pandas()


def load_common_data_polars(common_path: Path) -> dict[str, pl.DataFrame]:
    """
    Load common data files (NCF, BESS efficiency, degradation) using Polars.

    Parameters
    ----------
    common_path : Path
        Path to the common/ directory

    Returns
    -------
    dict[str, pl.DataFrame]
        Dictionary with 'ncf', 'bess_eff', 'degradation' DataFrames
    """
    result = {}

    ncf_path = common_path / "ncf.csv"
    if ncf_path.exists():
        result["ncf"] = read_csv_polars(ncf_path)

    bess_eff_path = common_path / "bess_efficiency.csv"
    if bess_eff_path.exists():
        result["bess_eff"] = read_csv_polars(bess_eff_path)

    degr_path = common_path / "solar_degradation.csv"
    if degr_path.exists():
        df = read_csv_polars(degr_path)
        if "Deg" in df.columns:
            df = df.rename({"Deg": "solar_degradation"})
        result["degradation"] = df

    return result


def load_series_data_polars(series_path: Path) -> dict[str, pl.DataFrame]:
    """
    Load series data (spot prices, curtailment) using Polars.
    """
    result = {}

    spot_path = series_path / "spot.csv"
    if spot_path.exists():
        df = read_csv_polars(spot_path)
        if "ValgestaMedio" in df.columns:
            df = df.rename({"ValgestaMedio": "Price USD/MWh"})
        result["spot"] = df

    curt_path = series_path / "curtailment.csv"
    if curt_path.exists():
        result["curtailment"] = read_csv_polars(curt_path)

    return result


def expand_degradation_to_monthly(degr_df: pl.DataFrame) -> pl.DataFrame:
    """
    Expand annual degradation data to monthly if needed.

    Uses a cross join to replicate annual values across all 12 months.
    """
    if "month" in degr_df.columns:
        return degr_df

    months = pl.DataFrame({"month": list(range(1, 13))})
    degr_annual = degr_df.select(["year", "solar_degradation"])
    result = degr_annual.join(months, how="cross")

    return result.select(["year", "month", "solar_degradation"])


def filter_data_by_years(
    df: pl.DataFrame,
    year_start: int,
    year_end: int,
    month_start: int = 1,
) -> pl.DataFrame:
    """
    Filter DataFrame to specified year range with optional month filter.
    """
    filtered = df.filter(
        (pl.col("year") >= year_start) & (pl.col("year") <= year_end)
    )

    if month_start > 1:
        filtered = filtered.filter(
            ~((pl.col("year") == year_start) & (pl.col("month") < month_start))
        )

    return filtered


def clean_hourly_data(df: pl.DataFrame) -> pl.DataFrame:
    """
    Clean hourly data by removing hour 25 and Feb 29.
    """
    return df.filter(
        (pl.col("hour") != 25)
        & ~((pl.col("month") == 2) & (pl.col("day") == 29))
    ).sort(["year", "month", "day", "hour"])


def merge_optimization_data(
    spot_df: pl.DataFrame,
    ncf_df: pl.DataFrame,
    curt_df: pl.DataFrame,
    degr_df: pl.DataFrame,
    year_start: int,
) -> pl.DataFrame:
    """
    Merge all data sources for optimization.

    Performs multi-table joins using Polars expressions for
    spot prices, capacity factors, curtailment, and degradation data.
    """
    # Merge spot with NCF
    df = spot_df.join(ncf_df, on=["month", "day", "hour"], how="left")

    # Merge with curtailment
    curt_cols = ["year", "month", "day", "hour", "Curtailment"]
    curt_subset = curt_df.select([c for c in curt_cols if c in curt_df.columns])
    df = df.join(curt_subset, on=["year", "month", "day", "hour"], how="left")

    # Handle degradation (convert relative years to absolute if needed)
    degr_copy = degr_df.clone()
    if degr_copy["year"].max() < 1000:
        degr_copy = degr_copy.with_columns(
            (pl.col("year") + year_start).alias("year")
        )

    # Merge degradation
    if "month" in degr_copy.columns:
        df = df.join(
            degr_copy.select(["year", "month", "solar_degradation"]),
            on=["year", "month"],
            how="left",
        )
    else:
        df = df.join(
            degr_copy.select(["year", "solar_degradation"]),
            on=["year"],
            how="left",
        )

    # Fill NaN values
    df = df.with_columns(
        [
            pl.col("NCF").fill_null(0.0),
            pl.col("Curtailment").fill_null(0.0),
            pl.col("solar_degradation").fill_null(0.0),
        ]
    )

    return df


def polars_to_numpy_arrays(df: pl.DataFrame, columns: list[str]) -> dict:
    """
    Convert Polars DataFrame columns to numpy arrays efficiently.
    """
    import numpy as np

    result = {}
    for col in columns:
        if col in df.columns:
            result[col] = df[col].to_numpy()
    return result


# =============================================================================
# Lazy Loading Functions with Polars LazyFrame
# =============================================================================


def scan_csv_lazy(
    path: Path,
    encoding: str | None = None,
    **kwargs,
) -> pl.LazyFrame:
    """
    Create a lazy scan of a CSV file without loading it into memory.

    Polars LazyFrame enables query optimization and memory-efficient
    processing of large files by only executing computations when needed.
    """
    if encoding is None:
        encoding = DEFAULT_CSV_ENCODING

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        return pl.scan_csv(path, encoding=encoding, **kwargs)
    except Exception:
        try:
            return pl.scan_csv(path, encoding=FALLBACK_CSV_ENCODING, **kwargs)
        except Exception as e:
            raise ValueError(f"Could not scan {path}: {e}") from e


def should_use_lazy_loading(path: Path) -> bool:
    """
    Determine if lazy loading should be used based on file size.
    """
    if not path.exists():
        return False
    return path.stat().st_size > LAZY_LOADING_THRESHOLD_BYTES


def load_csv_smart(
    path: Path,
    encoding: str | None = None,
    force_lazy: bool = False,
    **kwargs,
) -> pl.DataFrame | pl.LazyFrame:
    """
    Intelligently load a CSV file, using lazy loading for large files.

    For files larger than LAZY_LOADING_THRESHOLD_BYTES (50 MB), returns a
    LazyFrame. Otherwise, returns an eager DataFrame.
    """
    if force_lazy or should_use_lazy_loading(path):
        return scan_csv_lazy(path, encoding, **kwargs)
    return read_csv_polars(path, encoding, **kwargs)


def filter_data_by_years_lazy(
    lf: pl.LazyFrame,
    year_start: int,
    year_end: int,
    month_start: int = 1,
) -> pl.LazyFrame:
    """
    Filter LazyFrame to specified year range (lazy operation).
    """
    filtered = lf.filter(
        (pl.col("year") >= year_start) & (pl.col("year") <= year_end)
    )

    if month_start > 1:
        filtered = filtered.filter(
            ~((pl.col("year") == year_start) & (pl.col("month") < month_start))
        )

    return filtered


def clean_hourly_data_lazy(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Clean hourly data using lazy evaluation.
    """
    return lf.filter(
        (pl.col("hour") != 25)
        & ~((pl.col("month") == 2) & (pl.col("day") == 29))
    ).sort(["year", "month", "day", "hour"])


def collect_with_streaming(
    lf: pl.LazyFrame,
    streaming: bool = True,
) -> pl.DataFrame:
    """
    Collect a LazyFrame with optional streaming mode.

    Streaming mode processes data in batches, which is more memory-efficient
    for very large datasets.
    """
    if streaming:
        return lf.collect(streaming=True)
    return lf.collect()


def process_optimization_data_lazy(
    spot_lf: pl.LazyFrame,
    ncf_lf: pl.LazyFrame,
    curt_lf: pl.LazyFrame,
    degr_lf: pl.LazyFrame,
    year_start: int,
    year_end: int,
    month_start: int = 1,
    ncf_scale: float = 1.0,
) -> pl.DataFrame:
    """
    Process optimization data using lazy evaluation for memory efficiency.

    All operations are lazily defined and then collected once at the end,
    allowing Polars to optimize the query plan.
    """
    # Filter and clean spot data (lazy)
    spot_filtered = filter_data_by_years_lazy(
        spot_lf, year_start, year_end, month_start
    )
    spot_clean = clean_hourly_data_lazy(spot_filtered)

    # Filter and clean curtailment data (lazy)
    curt_filtered = filter_data_by_years_lazy(
        curt_lf, year_start, year_end, month_start
    )
    curt_clean = clean_hourly_data_lazy(curt_filtered)

    # Join spot with NCF (lazy)
    result = spot_clean.join(ncf_lf, on=["month", "day", "hour"], how="left")

    # Join with curtailment (lazy)
    curt_subset = curt_clean.select(
        ["year", "month", "day", "hour", "Curtailment"]
    )
    result = result.join(
        curt_subset, on=["year", "month", "day", "hour"], how="left"
    )

    # Process degradation (lazy)
    degr_work = degr_lf.with_columns(
        pl.when(pl.col("year").max() < 1000)
        .then(pl.col("year") + year_start)
        .otherwise(pl.col("year"))
        .alias("year")
    )

    result = result.join(
        degr_work.select(["year", "month", "solar_degradation"]),
        on=["year", "month"],
        how="left",
    )

    # Fill nulls and apply NCF scale (lazy)
    result = result.with_columns(
        [
            pl.col("NCF").fill_null(0.0),
            pl.col("Curtailment").fill_null(0.0),
            pl.col("solar_degradation").fill_null(0.0),
        ]
    )

    if ncf_scale != 1.0:
        result = result.with_columns(
            pl.col("NCF").mul(ncf_scale).clip(lower_bound=0.0)
        )

    # Collect with streaming for memory efficiency
    return collect_with_streaming(result)
