# src/services/data_loader.py
# -*- coding: utf-8 -*-
"""
Centralized DataLoader for the Energy Market Dashboard.

Provides:
- Parallel Arrow file loading
- Integrated cache (memory + disk)
- Unified API for all callbacks
- Elimination of duplicate code across tabs
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional
import threading
import logging

import polars as pl

from .smart_cache import prices_cache, geo_cache, cached
from .common_data import (
    DATA_ROOT, PRICE_COL, BAR_COL, Y, M, D, H,
    years_from_range,
    with_date,
    read_nodos, read_hydros,
    resolve_barras_exactas, resolve_condiciones_exactas,
    build_paths_verbose,
)

logger = logging.getLogger(__name__)


# ============================================================
# Parallel Arrow File Loading
# ============================================================

def _scan_single_file(path: Path, scenario: str) -> Optional[pl.LazyFrame]:
    """
    Scan a single Arrow file and normalize columns.

    Returns None if file doesn't exist or there's an error.
    """
    if not path.exists():
        logger.debug("File not found: %s", path)
        return None

    try:
        lf = pl.scan_ipc(path.as_posix(), memory_map=True)
        original_cols = set(lf.collect_schema().names())
        price_present = ("Valor" in original_cols) or (PRICE_COL in original_cols)

        # Extract node and condition from filename
        # Supported patterns:
        #   - "{scenario}_{node}_{condition}.arrow"
        #   - "{scenario} - {node}_{condition}.arrow"
        stem = path.stem
        if stem.startswith(f"{scenario}_"):
            rest = stem[len(scenario) + 1:]
        elif stem.startswith(f"{scenario} - "):
            rest = stem[len(scenario) + 3:]
        else:
            rest = stem

        if "_" in rest:
            node, condition = rest.rsplit("_", 1)
        else:
            node, condition = rest, ""

        # Normalize temporal column names
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
            lf = lf.with_columns(pl.col("Valor").cast(pl.Float64).alias(PRICE_COL))
        elif PRICE_COL in original_cols:
            lf = lf.with_columns(pl.col(PRICE_COL).cast(pl.Float64))
        else:
            lf = lf.with_columns(pl.lit(None, dtype=pl.Float64).alias(PRICE_COL))

        # Add Node/Condition if they don't exist
        if "Condicion" not in original_cols:
            lf = lf.with_columns(pl.lit(condition).alias("Condicion"))
        if "Barra" not in original_cols:
            lf = lf.with_columns(pl.lit(node).alias("Barra"))
        if BAR_COL not in original_cols:
            lf = lf.with_columns(pl.col("Barra").alias(BAR_COL))

        if not price_present:
            logger.warning("File skipped due to missing price column: %s", path)
            return None

        missing_temporal = [c for c in (Y, M, D, H) if c not in original_cols]
        if missing_temporal:
            logger.warning("File with missing temporal columns %s: %s", missing_temporal, path)

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
        scenario: Scenario name (for filename parsing)
        max_workers: Maximum number of threads

    Returns:
        Concatenated LazyFrame or None if no data
    """
    if not paths:
        logger.info("scan_arrow_parallel with no paths - nothing to load (scenario=%s)", scenario)
        return None

    # Filter only existing files (fast, no parallel I/O)
    existing = [p for p in paths if p.exists()]
    if not existing:
        logger.warning("No paths found on disk for scenario=%s (paths=%d)", scenario, len(paths))
        return None

    # Adjust workers by file count
    workers = min(max_workers, len(existing), 16)

    # Load in parallel
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
        logger.warning("Could not scan existing Arrow files (scenario=%s, paths=%d)", scenario, len(existing))
        return None

    # Concatenate all LazyFrames
    return pl.concat(lazy_frames, how="diagonal_relaxed")


# ============================================================
# Main DataLoader
# ============================================================

class DashboardDataLoader:
    """
    Centralized loader for the dashboard.

    Usage:
        loader = DashboardDataLoader()
        df = loader.load_prices(
            year_range=[2026, 2030],
            bars=["Node1", "Node2"],
            scenarios=["Base", "Sensitivity1"],
            hydrology=["Dry", "Normal"],
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

        self._nodos_cache: Optional[pl.DataFrame] = None
        self._hydros_cache: Optional[pl.DataFrame] = None
        self._initialized = True

    def _get_nodos(self) -> pl.DataFrame:
        """Get nodes table with cache."""
        if self._nodos_cache is None:
            self._nodos_cache = read_nodos()
        return self._nodos_cache

    def _get_hydros(self) -> pl.DataFrame:
        """Get hydrology table with cache."""
        if self._hydros_cache is None:
            self._hydros_cache = read_hydros()
        return self._hydros_cache

    def invalidate_metadata(self):
        """Invalidate metadata caches (nodes, hydrology)."""
        self._nodos_cache = None
        self._hydros_cache = None

    @cached(cache=prices_cache)
    def load_prices(
        self,
        year_range: tuple[int, int] | list[int],
        bars: Optional[List[str]] = None,
        scenarios: Optional[List[str]] = None,
        hydrology: Optional[List[str] | str] = None,
        include_metadata: bool = True,
    ) -> pl.DataFrame:
        """
        Load spot price data with filters.

        Args:
            year_range: Year range (tuple) or list of years
            bars: List of nodes/equivalents to load
            scenarios: List of scenarios
            hydrology: Hydrology filter (list or string)
            include_metadata: Whether to include joins with nodes/hydrology

        Returns:
            DataFrame with standard columns:
            [Y, M, D, H, date, ts, Scenario, BAR_COL, Node,
             Condition, Hydrology, Equivalent, PRICE_COL]
        """
        years = years_from_range(year_range)
        if not years:
            return pl.DataFrame()

        if not scenarios:
            logger.warning("load_prices called without scenarios -> returning empty")
            return pl.DataFrame()

        bars = bars or []

        all_lfs: List[pl.LazyFrame] = []

        for scen in scenarios:
            # Resolve filters
            conditions = resolve_condiciones_exactas(scen, hydrology)
            nodes = resolve_barras_exactas(scen, bars, logs=None)

            if not nodes or not conditions:
                continue

            # Build paths
            paths, _ = build_paths_verbose(scen, years, nodes, conditions)

            # Load in parallel
            lf_scen = scan_arrow_parallel(paths, scen, max_workers=8)

            if lf_scen is None:
                continue

            # Add date columns and scenario
            lf_scen = with_date(lf_scen).with_columns(
                pl.lit(scen).alias("Escenario")
            )

            # Joins with metadata if requested
            # OPTIMIZATION: Filter metadata tables BEFORE join (filter-before-join pattern)
            if include_metadata:
                # Join with nodes to get Equivalent
                # Pre-filter nodes by scenario and bars (if provided)
                nodos = self._get_nodos().filter(pl.col("Escenario") == scen)
                if bars:
                    nodos = nodos.filter(pl.col("Equivalente").is_in(bars))

                lf_scen = lf_scen.join(
                    nodos.lazy().select(["Barra", "Equivalente"]),
                    left_on="Barra",
                    right_on="Barra",
                    how="inner" if bars else "left",
                ).with_columns(
                    pl.when(pl.col("Equivalente").is_null())
                    .then(pl.lit("N/A"))
                    .otherwise(pl.col("Equivalente"))
                    .alias("Equivalente")
                )

                # Join with hydrology
                # Pre-filter hydros by scenario and hydrology (if provided)
                hydros = self._get_hydros().filter(pl.col("Escenario") == scen)
                if hydrology:
                    if isinstance(hydrology, (list, tuple)):
                        hydros = hydros.filter(pl.col("Hydrology").is_in(list(hydrology)))
                    else:
                        hydros = hydros.filter(pl.col("Hydrology") == hydrology)

                lf_scen = lf_scen.join(
                    hydros.lazy().select(["Condicion", "Hydrology"]),
                    on="Condicion",
                    how="inner" if hydrology else "left",
                )
            else:
                # No metadata joins - apply direct filters on Node
                if bars:
                    lf_scen = lf_scen.filter(pl.col("Barra").is_in(bars))

            all_lfs.append(lf_scen)

        if not all_lfs:
            return pl.DataFrame()

        # Concatenate and materialize
        lf = pl.concat(all_lfs, how="diagonal_relaxed")

        # Select standard columns
        standard_cols = [
            Y, M, D, H, "date", "ts",
            "Escenario", BAR_COL, "Barra",
            "Condicion", "Hydrology", "Equivalente",
            PRICE_COL,
        ]
        available_cols = set(lf.collect_schema().names())
        cols_to_select = [c for c in standard_cols if c in available_cols]

        return lf.select(cols_to_select).collect()

    def load_prices_uncached(
        self,
        year_range: tuple[int, int] | list[int],
        bars: Optional[List[str]] = None,
        scenarios: Optional[List[str]] = None,
        hydrology: Optional[List[str] | str] = None,
    ) -> pl.DataFrame:
        """Uncached version for frequently changing data."""
        return self._load_prices_internal(year_range, bars, scenarios, hydrology)

    def _load_prices_internal(
        self,
        year_range,
        bars,
        scenarios,
        hydrology,
    ) -> pl.DataFrame:
        """Internal implementation without cache."""
        return self.load_prices.__wrapped__(
            self, year_range, bars, scenarios, hydrology
        )


# ============================================================
# Global Instance
# ============================================================

# Globally accessible singleton
data_loader = DashboardDataLoader()


# ============================================================
# Convenience Functions
# ============================================================

def load_filtered_data(
    year_range,
    bars_equivalente,
    scenario,
    hydrology,
    compare_mode: str = "average",
) -> pl.DataFrame:
    """
    Convenience function to replace _load_filtered_df() in callbacks.

    Compatible with existing function signature.

    Args:
        year_range: Year range
        bars_equivalente: List of nodes
        scenario: Scenario(s) to filter
        hydrology: Hydrology(ies) to filter
        compare_mode: Comparison mode:
            - "average": Average everything (classic behavior)
            - "scenario": Compare scenarios (take first hydrology/node)
            - "hydrology": Compare hydrology (take first scenario/node)
            - "node": Compare nodes (take first scenario/hydrology)

    Returns:
        DataFrame filtered according to comparison mode
    """
    scenarios = (
        scenario
        if isinstance(scenario, (list, tuple))
        else ([scenario] if scenario else [])
    )

    hydrology_list = (
        hydrology
        if isinstance(hydrology, (list, tuple))
        else ([hydrology] if hydrology else [])
    )

    bars_list = bars_equivalente or []

    # Apply comparison logic
    if compare_mode == "scenario":
        # Compare scenarios: use all scenarios, but only first hydrology/node
        scenarios_to_use = scenarios if scenarios else []
        hydrology_to_use = hydrology_list[0] if hydrology_list else None
        bars_to_use = bars_list[:1] if bars_list else []

    elif compare_mode == "hydrology":
        # Compare hydrology: use all hydrology, but only first scenario/node
        scenarios_to_use = scenarios[:1] if scenarios else []
        hydrology_to_use = hydrology_list if hydrology_list else None
        bars_to_use = bars_list[:1] if bars_list else []

    elif compare_mode == "node":
        # Compare nodes: use all nodes, but only first scenario/hydrology
        scenarios_to_use = scenarios[:1] if scenarios else []
        hydrology_to_use = hydrology_list[0] if hydrology_list else None
        bars_to_use = bars_list if bars_list else []

    else:  # "average"
        # Classic mode: use everything (will be averaged later)
        scenarios_to_use = scenarios
        hydrology_to_use = hydrology
        bars_to_use = bars_list

    return data_loader.load_prices(
        year_range=year_range,
        bars=bars_to_use,
        scenarios=scenarios_to_use,
        hydrology=hydrology_to_use,
    )


__all__ = [
    "DashboardDataLoader",
    "data_loader",
    "load_filtered_data",
    "scan_arrow_parallel",
]
