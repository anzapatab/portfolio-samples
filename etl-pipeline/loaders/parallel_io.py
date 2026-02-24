"""
Parallel I/O Utilities for CSV Loading

Provides optimized functions for loading multiple CSV files in parallel
using ThreadPoolExecutor. Supports per-file encoding/kwargs, optional
post-processing callbacks, and specialized profile loading.

Source: Production pipeline for electricity market unit commitment solver.
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Callable, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging


def load_csvs_parallel(
    files: Dict[str, str],
    max_workers: int = 4,
    read_csv_kwargs: Optional[Dict[str, Dict[str, Any]]] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Load multiple CSV files in parallel.

    Args:
        files: Dict {name: file_path}
        max_workers: Number of ThreadPool workers
        read_csv_kwargs: Dict {file_name: kwargs} for pd.read_csv per file
        logger: Optional logger

    Returns:
        Dict {name: DataFrame}

    Example:
        ```python
        files = {
            "demand": "data/processed/demand.csv",
            "lines": "data/parameters/line_parameters.csv"
        }
        # Per-file kwargs
        kwargs = {
            "lines": {"encoding": "cp1252"}
        }
        dfs = load_csvs_parallel(files, max_workers=4, read_csv_kwargs=kwargs)
        df_demand = dfs["demand"]
        ```
    """
    if logger:
        logger.info(
            f"Loading {len(files)} CSV files in parallel (workers={max_workers})..."
        )

    read_kwargs_by_file = read_csv_kwargs or {}
    results = {}

    def load_single_csv(name: str, path: str) -> tuple:
        """Load a single CSV file."""
        try:
            file_kwargs = read_kwargs_by_file.get(name, {})
            df = pd.read_csv(path, **file_kwargs)
            if logger:
                logger.debug(f"  {name}: {len(df)} rows")
            return name, df, None
        except Exception as e:
            if logger:
                logger.error(f"  {name}: Error - {e}")
            return name, None, e

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {
            executor.submit(load_single_csv, name, path): name
            for name, path in files.items()
        }

        for future in as_completed(future_to_name):
            name, df, error = future.result()
            if error is None:
                results[name] = df
            else:
                raise RuntimeError(f"Error loading {name}: {error}")

    if logger:
        total_rows = sum(len(df) for df in results.values())
        logger.info(f"{len(results)} files loaded ({total_rows:,} total rows)")

    return results


def load_and_process_csvs_parallel(
    files: Dict[str, str],
    processors: Optional[Dict[str, Callable]] = None,
    max_workers: int = 4,
    read_csv_kwargs: Optional[Dict[str, Dict[str, Any]]] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Load and process multiple CSVs in parallel.

    Args:
        files: Dict {name: file_path}
        processors: Dict {name: processing_function} (optional)
        max_workers: Number of workers
        read_csv_kwargs: Dict {file_name: kwargs} for pd.read_csv per file
        logger: Optional logger

    Returns:
        Dict {name: processed DataFrame}

    Example:
        ```python
        def process_demand(df):
            df['demand'] = df['demand'].fillna(0)
            return df

        files = {"demand": "data/demand.csv"}
        processors = {"demand": process_demand}
        kwargs = {"demand": {"encoding": "utf-8"}}

        dfs = load_and_process_csvs_parallel(files, processors, read_csv_kwargs=kwargs)
        ```
    """
    if logger:
        logger.info(
            f"Loading and processing {len(files)} files in parallel..."
        )

    read_kwargs_by_file = read_csv_kwargs or {}
    processors = processors or {}
    results = {}

    def load_and_process(name: str, path: str) -> tuple:
        """Load and process a single CSV."""
        try:
            file_kwargs = read_kwargs_by_file.get(name, {})
            df = pd.read_csv(path, **file_kwargs)

            # Apply processor if available
            if name in processors:
                df = processors[name](df)

            if logger:
                logger.debug(f"  {name}: {len(df)} rows (processed)")

            return name, df, None
        except Exception as e:
            if logger:
                logger.error(f"  {name}: Error - {e}")
            return name, None, e

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {
            executor.submit(load_and_process, name, path): name
            for name, path in files.items()
        }

        for future in as_completed(future_to_name):
            name, df, error = future.result()
            if error is None:
                results[name] = df
            else:
                raise RuntimeError(f"Error processing {name}: {error}")

    if logger:
        logger.info(f"{len(results)} files processed")

    return results


def load_generation_profiles_parallel(
    base_path: str,
    profile_files: Dict[str, str],
    column_mapping: Optional[Dict[str, str]] = None,
    required_columns: Optional[List[str]] = None,
    max_workers: int = 4,
    logger: Optional[logging.Logger] = None,
) -> pd.DataFrame:
    """
    Load multiple generation profiles in parallel and concatenate them.

    Specialized function for loading files like:
    - solar_profiles.csv
    - wind_profiles.csv
    - etc.

    Args:
        base_path: Base path where the files reside
        profile_files: Dict {type: filename}
        column_mapping: Column name mapping
        required_columns: List of columns to keep
        max_workers: Number of workers
        logger: Optional logger

    Returns:
        Concatenated DataFrame with all profiles

    Example:
        ```python
        profile_files = {
            "solar": "solar_profiles.csv",
            "wind": "wind_profiles.csv"
        }

        column_mapping = {
            "NAME": "Plant",
            "GenRating": "Pmax"
        }

        df_gen = load_generation_profiles_parallel(
            "data/processed",
            profile_files,
            column_mapping,
            required_columns=["PERIOD", "Plant", "Pmax"]
        )
        ```
    """
    if logger:
        logger.info(
            f"Loading {len(profile_files)} generation profiles in parallel..."
        )

    base = Path(base_path)

    def load_and_clean_profile(profile_type: str, filename: str) -> tuple:
        """Load and clean a generation profile."""
        try:
            df = pd.read_csv(base / filename)

            # Remove null VariableCost for certain types
            if profile_type in ["diesel", "biomass", "gas"]:
                df = df[df["VariableCost"].notna()].reset_index(drop=True)

            # Rename columns
            if column_mapping:
                df.rename(columns=column_mapping, inplace=True)

            # Filter required columns
            if required_columns:
                existing_cols = [
                    col for col in required_columns if col in df.columns
                ]
                df = df[existing_cols].copy()

            if logger:
                logger.debug(f"  {profile_type}: {len(df)} records")

            return profile_type, df, None

        except Exception as e:
            if logger:
                logger.error(f"  {profile_type}: Error - {e}")
            return profile_type, None, e

    # Load in parallel
    dfs = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_type = {
            executor.submit(load_and_clean_profile, ptype, filename): ptype
            for ptype, filename in profile_files.items()
        }

        for future in as_completed(future_to_type):
            ptype, df, error = future.result()
            if error is None and df is not None:
                dfs.append(df)
            elif error is not None:
                if logger:
                    logger.warning(f"Skipping profile {ptype}: {error}")

    # Concatenate
    if not dfs:
        if logger:
            logger.error("Could not load any generation profiles")
        return pd.DataFrame()

    df_combined: pd.DataFrame = pd.concat(dfs, ignore_index=True)

    if logger:
        logger.info(f"Profiles concatenated: {len(df_combined):,} total records")

    return df_combined
