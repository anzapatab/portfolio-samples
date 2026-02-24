"""
Parallel CSV-to-Parquet Converter

Converts raw CSV files organized by year into optimized Parquet format
using Polars for fast I/O and ProcessPoolExecutor for year-level parallelism.

Source: Production pipeline for electricity market simulation data.
"""

import polars as pl
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import logging

logger = logging.getLogger(__name__)


def process_year(year_folder: Path, output_year_dir: Path, file_extension=".csv"):
    """
    Convert all CSVs in a folder (one year) to Parquet using Polars.
    """
    try:
        output_year_dir.mkdir(parents=True, exist_ok=True)
        files = list(year_folder.glob(f"*{file_extension}"))

        if not files:
            msg = f"No files found in {year_folder}"
            logger.warning(msg)
            return msg

        for file in files:
            try:
                # Read CSV with Polars
                df = pl.read_csv(file, ignore_errors=True, low_memory=True)
                df = df.rechunk()  # memory optimization

                # Output path
                parquet_path = output_year_dir / f"{file.stem}.parquet"
                df.write_parquet(parquet_path, compression="snappy")

                logger.info(f"Converted: {file.name} -> {parquet_path}")
            except Exception as e:
                error_msg = f"Error in {file.name}: {e}"
                logger.error(error_msg)

        return f"Year {year_folder.name} processed ({len(files)} files)"
    except Exception as e:
        error_msg = f"Error processing folder {year_folder}: {e}"
        logger.error(error_msg)
        return error_msg


def convert_csv_to_parquet(
    raw_path: str,
    processed_path: str,
    file_extension=".csv",
    max_workers=os.cpu_count(),
):
    """
    Convert all CSV files in data/raw/{year}/ to Parquet in data/processed/{year}/.
    Parallel processing at the YEAR level using Polars + Logging.
    """
    raw_dir = Path(raw_path)
    processed_dir = Path(processed_path)

    if not raw_dir.exists():
        msg = f"Path not found: {raw_dir}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    year_folders = [folder for folder in raw_dir.iterdir() if folder.is_dir()]

    if not year_folders:
        logger.warning("No year folders found in data/raw.")
        return

    logger.info(
        f"Starting conversion: {len(year_folders)} folders found in {raw_dir}"
    )

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for year_folder in year_folders:
            output_year_dir = processed_dir / year_folder.name
            logger.info(f"Processing year: {year_folder.name}")
            futures.append(
                executor.submit(
                    process_year, year_folder, output_year_dir, file_extension
                )
            )

        for future in as_completed(futures):
            logger.info(future.result())

    logger.info("Conversion completed successfully.")
