# src/services/downsampling.py
# -*- coding: utf-8 -*-
"""
Intelligent downsampling for large time series visualization.

This module implements the LTTB (Largest Triangle Three Buckets) algorithm,
which reduces the number of points in a time series while preserving
the most important visual characteristics.

References:
- Original paper: https://skemman.is/bitstream/1946/15343/3/SS_MSthesis.pdf
- Sveinn Steinarsson, 2013
"""
from __future__ import annotations

from typing import Optional, Union
import numpy as np
import polars as pl
import pandas as pd


def lttb_downsample(
    x: Union[list, np.ndarray, pl.Series, pd.Series],
    y: Union[list, np.ndarray, pl.Series, pd.Series],
    threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Largest Triangle Three Buckets (LTTB) downsampling algorithm.

    Reduces a time series of N points to M points (threshold) while
    preserving the most important visual characteristics. Ideal for
    visualizing large datasets.

    The algorithm divides data into "buckets" and selects the most
    representative point from each bucket based on the area of the triangle
    formed with neighboring points.

    Args:
        x: Array of X values (typically timestamps or indices)
        y: Array of Y values (typically prices or measurements)
        threshold: Desired number of points in output (M)

    Returns:
        Tuple (x_downsampled, y_downsampled) with reduced arrays

    Raises:
        ValueError: If threshold < 2 or arrays have different lengths

    Examples:
        >>> # Large dataset with 100k points
        >>> x = np.arange(100000)
        >>> y = np.random.randn(100000).cumsum()
        >>>
        >>> # Reduce to 1000 points preserving visual shape
        >>> x_down, y_down = lttb_downsample(x, y, threshold=1000)
        >>> len(x_down)
        1000
        >>>
        >>> # Works with Polars Series
        >>> df = pl.DataFrame({"x": x, "y": y})
        >>> x_down, y_down = lttb_downsample(df["x"], df["y"], threshold=500)

    Notes:
        - For small datasets (< threshold), returns original data
        - Time complexity: O(n) where n is the original size
        - First and last points are always preserved
        - Much better than uniform downsampling for preserving visual features
    """
    # Convert to numpy arrays
    x = _to_numpy(x)
    y = _to_numpy(y)

    # Validations
    if len(x) != len(y):
        raise ValueError(f"x and y must have the same length. Got len(x)={len(x)}, len(y)={len(y)}")

    data_length = len(x)

    if threshold < 2:
        raise ValueError(f"threshold must be >= 2. Got {threshold}")

    if data_length <= threshold:
        # No downsampling needed
        return x, y

    # Initialize output arrays
    sampled_x = np.zeros(threshold)
    sampled_y = np.zeros(threshold)

    # Always include first point
    sampled_x[0] = x[0]
    sampled_y[0] = y[0]

    # Always include last point
    sampled_x[threshold - 1] = x[-1]
    sampled_y[threshold - 1] = y[-1]

    # Size of each bucket (interval between selected points)
    bucket_size = (data_length - 2) / (threshold - 2)

    # Index in output array
    sampled_index = 1

    # Index in input array
    a = 0  # Index of previously selected point

    for i in range(threshold - 2):
        # Calculate range of current bucket
        avg_range_start = int((i + 1) * bucket_size) + 1
        avg_range_end = int((i + 2) * bucket_size) + 1
        avg_range_end = min(avg_range_end, data_length)

        # Calculate average point of next bucket
        avg_x = 0.0
        avg_y = 0.0
        avg_range_length = avg_range_end - avg_range_start

        for j in range(avg_range_start, avg_range_end):
            avg_x += x[j]
            avg_y += y[j]

        if avg_range_length > 0:
            avg_x /= avg_range_length
            avg_y /= avg_range_length

        # Calculate range of current bucket to find best point
        range_offs = int(i * bucket_size) + 1
        range_to = int((i + 1) * bucket_size) + 1

        # Coordinates of previous point
        point_a_x = x[a]
        point_a_y = y[a]

        max_area = -1.0
        max_area_point = range_offs

        # Find the point with the largest triangle area
        for j in range(range_offs, range_to):
            # Calculate area of triangle formed by:
            # - previous point (a)
            # - candidate point (j)
            # - average point of next bucket (avg)
            area = abs(
                (point_a_x - avg_x) * (y[j] - point_a_y)
                - (point_a_x - x[j]) * (avg_y - point_a_y)
            ) * 0.5

            if area > max_area:
                max_area = area
                max_area_point = j

        # Select the point with largest area
        sampled_x[sampled_index] = x[max_area_point]
        sampled_y[sampled_index] = y[max_area_point]
        sampled_index += 1

        a = max_area_point  # This point becomes the previous for next iteration

    return sampled_x, sampled_y


def lttb_downsample_dataframe(
    df: Union[pl.DataFrame, pd.DataFrame],
    x_col: str,
    y_col: str,
    threshold: int,
    keep_cols: Optional[list[str]] = None,
) -> Union[pl.DataFrame, pd.DataFrame]:
    """
    Apply LTTB downsampling to a DataFrame while keeping additional columns.

    Args:
        df: Polars or Pandas DataFrame
        x_col: Name of X column (e.g., "date", "timestamp")
        y_col: Name of Y column (e.g., "price", "value")
        threshold: Desired number of points
        keep_cols: Additional columns to keep (uses nearest interpolation)

    Returns:
        Reduced DataFrame with the same columns

    Examples:
        >>> df = pl.DataFrame({
        ...     "timestamp": range(100000),
        ...     "price": np.random.randn(100000).cumsum(),
        ...     "node": ["Node1"] * 100000,
        ... })
        >>>
        >>> df_small = lttb_downsample_dataframe(
        ...     df, x_col="timestamp", y_col="price",
        ...     threshold=1000, keep_cols=["node"]
        ... )
        >>> len(df_small)
        1000
    """
    is_polars = isinstance(df, pl.DataFrame)

    # Convert to numpy for the algorithm
    if is_polars:
        x = df[x_col].to_numpy()
        y = df[y_col].to_numpy()
    else:
        x = df[x_col].values
        y = df[y_col].values

    # Apply downsampling
    x_down, y_down = lttb_downsample(x, y, threshold)

    # Create indices to recover original rows
    if is_polars:
        original_x = df[x_col].to_numpy()
    else:
        original_x = df[x_col].values

    # Find nearest indices in original array
    indices = np.searchsorted(original_x, x_down)
    indices = np.clip(indices, 0, len(df) - 1)

    # Build reduced DataFrame
    if is_polars:
        result = pl.DataFrame({
            x_col: x_down,
            y_col: y_down,
        })

        # Add additional columns
        if keep_cols:
            for col in keep_cols:
                if col in df.columns and col not in [x_col, y_col]:
                    result = result.with_columns(
                        pl.Series(name=col, values=[df[col][i] for i in indices])
                    )
    else:
        result = pd.DataFrame({
            x_col: x_down,
            y_col: y_down,
        })

        # Add additional columns
        if keep_cols:
            for col in keep_cols:
                if col in df.columns and col not in [x_col, y_col]:
                    result[col] = df.iloc[indices][col].values

    return result


def adaptive_downsample(
    df: Union[pl.DataFrame, pd.DataFrame],
    x_col: str,
    y_col: str,
    max_points: int = 10000,
    min_threshold: int = 1000,
) -> Union[pl.DataFrame, pd.DataFrame]:
    """
    Adaptive downsampling: only reduces if exceeds max_points.

    Args:
        df: DataFrame to reduce
        x_col: X column
        y_col: Y column
        max_points: Maximum allowed points
        min_threshold: Minimum points to keep if downsampling

    Returns:
        Original or reduced DataFrame as needed

    Examples:
        >>> # Small dataset - no reduction
        >>> small_df = pl.DataFrame({"x": range(100), "y": range(100)})
        >>> result = adaptive_downsample(small_df, "x", "y", max_points=1000)
        >>> len(result) == 100
        True
        >>>
        >>> # Large dataset - reduced
        >>> large_df = pl.DataFrame({"x": range(100000), "y": range(100000)})
        >>> result = adaptive_downsample(large_df, "x", "y", max_points=5000)
        >>> len(result) <= 5000
        True
    """
    data_length = len(df)

    if data_length <= max_points:
        # No downsampling needed
        return df

    # Calculate optimal threshold
    threshold = max(min_threshold, min(max_points, data_length // 2))

    return lttb_downsample_dataframe(df, x_col, y_col, threshold)


def _to_numpy(data: Union[list, np.ndarray, pl.Series, pd.Series]) -> np.ndarray:
    """Convert various data types to numpy array."""
    if isinstance(data, np.ndarray):
        return data
    elif isinstance(data, pl.Series):
        return data.to_numpy()
    elif isinstance(data, pd.Series):
        return data.values
    elif isinstance(data, list):
        return np.array(data)
    else:
        try:
            return np.array(data)
        except:
            raise TypeError(f"Cannot convert {type(data)} to numpy array")


# ============================================================
# UTILITIES
# ============================================================

def estimate_reduction_ratio(original_size: int, threshold: int) -> float:
    """
    Estimate the size reduction percentage.

    Examples:
        >>> estimate_reduction_ratio(100000, 1000)
        99.0
    """
    if original_size <= threshold:
        return 0.0
    return (1 - threshold / original_size) * 100


def should_downsample(data_size: int, threshold: int = 10000) -> bool:
    """
    Determine if downsampling is worthwhile.

    Args:
        data_size: Size of the dataset
        threshold: Threshold for deciding

    Returns:
        True if the dataset is large enough
    """
    return data_size > threshold


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "lttb_downsample",
    "lttb_downsample_dataframe",
    "adaptive_downsample",
    "should_downsample",
    "estimate_reduction_ratio",
]
