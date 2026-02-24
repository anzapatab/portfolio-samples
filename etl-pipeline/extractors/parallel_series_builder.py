"""
Parallel Time Series Builder

Reads thousands of Arrow/Feather files in parallel using ThreadPoolExecutor
(64 workers), constructs a pivoted DataFrame with Polars, and exports to Parquet.

Optimizations over original sequential approach:
1. Parallel file reading with ThreadPoolExecutor (64 workers)
2. Direct dict -> DataFrame construction (O(n) vs O(n^2) incremental merge)
3. Polars for final DataFrame construction and Parquet export

Source: Production pipeline for Monte Carlo simulation inputs (electricity market).
"""

import os
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import polars as pl
import pyarrow.feather as feather
import time
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration from environment
PROCESSED_BASE = os.environ.get("SERIES_DB_PATH", "./data/processed")
N_WORKERS = int(os.environ.get("N_WORKERS", 64))


def find_col(columns, candidates):
    """Case-insensitive column name search"""
    cols_lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in columns:
            return cand
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None


def find_arrow_file(folder, base_name):
    """Find Arrow/Feather file by base name"""
    if not os.path.isdir(folder):
        return None
    base_lower = base_name.lower()
    for fname in os.listdir(folder):
        name_no_ext, ext = os.path.splitext(fname)
        if name_no_ext.lower() == base_lower and ext.lower() in (
            ".arrow",
            ".feather",
            "",
        ):
            return os.path.join(folder, fname)
    return None


def process_single_arrow(args):
    """Process a single Arrow file - executed in parallel"""
    scenario, year_rel, series_name, processed_base = args

    folder = os.path.join(processed_base, "spot", scenario, str(year_rel))
    arrow_path = find_arrow_file(folder, series_name)

    if not arrow_path:
        return None, (scenario, year_rel, series_name, "not_found")

    try:
        # Fast read with PyArrow
        df = feather.read_feather(arrow_path)

        # Find columns
        month_c = find_col(df.columns, ["Month", "month", "MES", "Mes"])
        day_c = find_col(df.columns, ["Day", "day", "DIA", "Dia"])
        hour_c = find_col(df.columns, ["Hour", "hour", "HORA", "Hora"])
        valor_c = find_col(
            df.columns, ["Value", "value", "Valor", "valor", "VALOR"]
        )

        if not all([month_c, day_c, hour_c, valor_c]):
            return None, (scenario, year_rel, series_name, "missing_cols")

        col_name = f"{series_name}_{year_rel}"

        # Extract only the values (assuming consistent Month/Day/Hour order)
        values = df[valor_c].values

        return (col_name, values), None

    except Exception as e:
        return None, (scenario, year_rel, series_name, str(e))


def process_spot_files(csv_path, processed_base, output_dir):
    """Process all spot files in parallel"""

    logging.info(f"Reading: {csv_path}")

    # Read scenario CSV
    df_scenarios = pd.read_csv(csv_path, encoding="utf-8")

    # Find columns
    scenario_col = find_col(df_scenarios.columns, ["Scenario", "Escenario", "escenario"])
    yearrel_col = find_col(
        df_scenarios.columns,
        ["RelativeYear", "Year_relativo", "Year relativo", "YearRelativo"],
    )
    series_col = find_col(df_scenarios.columns, ["NodeSeries", "SerieNodo", "Serie_Nodo"])

    if not all([scenario_col, yearrel_col, series_col]):
        logging.error(
            f"Columns not found. Available: {df_scenarios.columns.tolist()}"
        )
        return

    # Get unique combinations
    unique_series = df_scenarios[
        [scenario_col, yearrel_col, series_col]
    ].drop_duplicates()
    logging.info(f"Unique series to process: {len(unique_series):,}")

    # Prepare tasks
    tasks = [
        (
            row[scenario_col],
            row[yearrel_col],
            row[series_col],
            processed_base,
        )
        for _, row in unique_series.iterrows()
    ]

    # Process in parallel
    logging.info(f"Processing with {N_WORKERS} workers...")
    results = {}
    missing = []

    with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
        futures = {
            executor.submit(process_single_arrow, task): task for task in tasks
        }

        for future in tqdm(
            as_completed(futures), total=len(tasks), desc="Reading Arrow"
        ):
            result, error = future.result()
            if result:
                col_name, values = result
                if col_name not in results:  # Avoid duplicates
                    results[col_name] = values
            if error:
                missing.append(error)

    logging.info(
        f"Processed: {len(results):,} series. Missing: {len(missing):,}"
    )

    if not results:
        logging.error("No series processed")
        return

    # Build DataFrame with Polars (faster than pandas)
    logging.info("Building final DataFrame...")

    # Create temporal base (8760 hours)
    # Assuming non-leap year
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    months = []
    days = []
    hours = []
    for m, n_days in enumerate(days_per_month, 1):
        for d in range(1, n_days + 1):
            for h in range(1, 25):
                months.append(m)
                days.append(d)
                hours.append(h)

    # Create base DataFrame
    data = {
        "Month": months,
        "Day": days,
        "Hour": hours,
    }

    # Add all series
    n_hours = 8760
    for col_name, values in results.items():
        if len(values) == n_hours:
            data[col_name] = values
        else:
            logging.warning(
                f"Series {col_name} has {len(values)} values, expected {n_hours}"
            )

    df_final = pl.DataFrame(data)

    # Save
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "SeriesSpot_Pivot.parquet")
    df_final.write_parquet(out_path, compression="snappy")

    logging.info(f"Saved: {out_path}")
    logging.info(
        f"Dimensions: {df_final.shape[0]:,} rows x {df_final.shape[1]:,} columns"
    )

    if missing:
        logging.info("First 10 missing:")
        for m in missing[:10]:
            logging.info(f"  {m}")


def main():
    start = time.perf_counter()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "inputs", "scenarios.csv")
    out_dir = os.path.join(script_dir, "out")

    if not os.path.exists(csv_path):
        logging.error(f"File not found: {csv_path}")
        return

    process_spot_files(csv_path, PROCESSED_BASE, out_dir)

    elapsed = time.perf_counter() - start
    logging.info(f"\nTotal time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()
