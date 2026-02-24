"""
Parallel Arrow/IPC File Scanner

Loads multiple Arrow/Feather files in parallel using ThreadPoolExecutor,
normalizes column schemas, and concatenates into a unified LazyFrame.

Features:
1. Parallel file scanning with ThreadPoolExecutor (up to 16 workers)
2. Automatic column normalization (case-insensitive matching)
3. Schema-aware type casting for temporal columns
4. Lazy evaluation with Polars LazyFrame for query optimization
5. Smart sequential/parallel switching based on file count

Source: Production data loader for electricity market price explorer dashboard.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Dict, Any
import threading
import logging

import polars as pl

logger = logging.getLogger(__name__)

# Standard column names
PRICE_COL = "price_usd_mwh"
BAR_COL = "bar_id"
Y, M, D, H = "year", "month", "day", "hour"


def _scan_single_file(path: Path, scenario: str) -> Optional[pl.LazyFrame]:
    """
    Scan a single Arrow file and normalize columns.

    Returns None if the file does not exist or there is an error.
    """
    if not path.exists():
        logger.debug("File not found: %s", path)
        return None

    try:
        lf = pl.scan_ipc(path.as_posix(), memory_map=True)
        original_cols = set(lf.collect_schema().names())
        price_present = ("Valor" in original_cols) or (PRICE_COL in original_cols)

        # Extract bar and condition from filename
        # Supported patterns:
        #   - "{scenario}_{bar}_{condition}.arrow"
        #   - "{scenario} - {bar}_{condition}.arrow"
        stem = path.stem
        if stem.startswith(f"{scenario}_"):
            rest = stem[len(scenario) + 1:]
        elif stem.startswith(f"{scenario} - "):
            rest = stem[len(scenario) + 3:]
        else:
            rest = stem

        if "_" in rest:
            bar, condition = rest.rsplit("_", 1)
        else:
            bar, condition = rest, ""

        # Normalize temporal column names (case-insensitive)
        rename_map = {}
        for old, new in [
            ("Year", Y), ("year", Y), ("YEAR", Y),
            ("Month", M), ("month", M), ("MONTH", M),
            ("Day", D), ("day", D), ("DAY", D),
            ("Hour", H), ("hour", H), ("HOUR", H),
        ]:
            if old in original_cols and new not in original_cols:
                rename_map[old] = new

        if rename_map:
            lf = lf.rename(rename_map)
            for old, new in rename_map.items():
                original_cols.discard(old)
                original_cols.add(new)

        # Ensure temporal column types
        type_casts = []
        for col, dtype in {Y: pl.Int32, M: pl.Int8, D: pl.Int8, H: pl.Int8}.items():
            if col not in original_cols:
                type_casts.append(pl.lit(None, dtype=dtype).alias(col))
            else:
                type_casts.append(pl.col(col).cast(dtype))

        if type_casts:
            lf = lf.with_columns(type_casts)

        # Normalize price column
        if "Valor" in original_cols:
            lf = lf.with_columns(
                pl.col("Valor").cast(pl.Float64).alias(PRICE_COL)
            )
        elif PRICE_COL in original_cols:
            lf = lf.with_columns(pl.col(PRICE_COL).cast(pl.Float64))
        else:
            lf = lf.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(PRICE_COL)
            )

        # Add Bar/Condition columns if not present
        if "Condition" not in original_cols:
            lf = lf.with_columns(pl.lit(condition).alias("Condition"))
        if "Bar" not in original_cols:
            lf = lf.with_columns(pl.lit(bar).alias("Bar"))
        if BAR_COL not in original_cols:
            lf = lf.with_columns(pl.col("Bar").alias(BAR_COL))

        if not price_present:
            logger.warning(
                "File skipped (no price column): %s", path
            )
            return None

        missing_temporal = [c for c in (Y, M, D, H) if c not in original_cols]
        if missing_temporal:
            logger.warning(
                "File with missing temporal columns %s: %s",
                missing_temporal,
                path,
            )

        return lf

    except Exception as exc:
        logger.warning("Error scanning file %s: %s", path, exc, exc_info=True)
        return None


def scan_arrow_parallel(
    paths: List[Path],
    scenario: str,
    max_workers: int = 8,
) -> Optional[pl.LazyFrame]:
    """
    Load multiple Arrow files in parallel.

    Args:
        paths: List of paths to .arrow files
        scenario: Scenario name (for parsing filenames)
        max_workers: Maximum number of threads

    Returns:
        Concatenated LazyFrame or None if no data
    """
    if not paths:
        logger.info(
            "scan_arrow_parallel with no paths (scenario=%s)", scenario
        )
        return None

    # Filter to existing files only
    existing = [p for p in paths if p.exists()]
    if not existing:
        logger.warning(
            "No paths found on disk for scenario=%s (paths=%d)",
            scenario,
            len(paths),
        )
        return None

    # Adjust workers based on file count
    workers = min(max_workers, len(existing), 16)

    # Load files
    lazy_frames: List[pl.LazyFrame] = []

    if workers <= 2 or len(existing) <= 4:
        # For few files, sequential is more efficient
        for p in existing:
            lf = _scan_single_file(p, scenario)
            if lf is not None:
                lazy_frames.append(lf)
    else:
        # Parallel for many files
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_scan_single_file, p, scenario): p
                for p in existing
            }

            for future in as_completed(futures):
                lf = future.result()
                if lf is not None:
                    lazy_frames.append(lf)

    if not lazy_frames:
        logger.warning(
            "Could not scan any Arrow files (scenario=%s, paths=%d)",
            scenario,
            len(existing),
        )
        return None

    # Concatenate all LazyFrames
    return pl.concat(lazy_frames, how="diagonal_relaxed")


class ParallelDataLoader:
    """
    Centralized data loader with parallel Arrow scanning.

    Usage:
        loader = ParallelDataLoader()
        df = loader.load_prices(
            year_range=[2026, 2030],
            bars=["Node1", "Node2"],
            scenarios=["Base", "Sensitivity1"],
        )
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern to avoid multiple instances."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._metadata_cache: Dict[str, Any] = {}
        self._initialized = True

    def invalidate_metadata(self):
        """Invalidate cached metadata."""
        self._metadata_cache.clear()

    def load_prices(
        self,
        year_range: tuple[int, int] | list[int],
        bars: Optional[List[str]] = None,
        scenarios: Optional[List[str]] = None,
        data_root: Optional[Path] = None,
    ) -> pl.DataFrame:
        """
        Load price data with parallel Arrow scanning.

        Args:
            year_range: Range of years (tuple) or list of years
            bars: List of bars/nodes to load
            scenarios: List of scenarios
            data_root: Root directory for data files

        Returns:
            DataFrame with standard columns:
            [year, month, day, hour, scenario, bar_id, price_usd_mwh]
        """
        if not scenarios:
            logger.warning("load_prices called without scenarios -> returning empty")
            return pl.DataFrame()

        # Determine year list
        if isinstance(year_range, (list, tuple)) and len(year_range) == 2:
            years = list(range(year_range[0], year_range[1] + 1))
        else:
            years = list(year_range)

        if not years:
            return pl.DataFrame()

        root = data_root or Path("./data/processed")
        all_lfs: List[pl.LazyFrame] = []

        for scen in scenarios:
            # Build file paths
            paths = []
            scen_dir = root / scen
            if scen_dir.exists():
                for year in years:
                    year_dir = scen_dir / str(year)
                    if year_dir.exists():
                        paths.extend(year_dir.glob("*.arrow"))

            # Scan in parallel
            lf_scen = scan_arrow_parallel(list(paths), scen, max_workers=8)

            if lf_scen is None:
                continue

            # Add scenario column
            lf_scen = lf_scen.with_columns(pl.lit(scen).alias("scenario"))

            # Filter bars if specified
            if bars:
                lf_scen = lf_scen.filter(pl.col("Bar").is_in(bars))

            all_lfs.append(lf_scen)

        if not all_lfs:
            return pl.DataFrame()

        # Concatenate and materialize
        lf = pl.concat(all_lfs, how="diagonal_relaxed")

        # Select standard columns
        standard_cols = [
            Y, M, D, H,
            "scenario", BAR_COL, "Bar",
            "Condition",
            PRICE_COL,
        ]
        available_cols = set(lf.collect_schema().names())
        cols_to_select = [c for c in standard_cols if c in available_cols]

        return lf.select(cols_to_select).collect()
