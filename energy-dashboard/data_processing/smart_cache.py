# src/services/smart_cache.py
# -*- coding: utf-8 -*-
"""
Smart Cache System for the Energy Market Dashboard.

Features:
- In-memory cache (LRU) for fast access
- Disk cache for persistence between sessions
- TTL (time-to-live) invalidation
- Efficient binary serialization with Arrow IPC + LZ4
- Thread-safe for concurrent callback usage
"""
from __future__ import annotations

import hashlib
import json
import time
import threading
from pathlib import Path
from functools import wraps
from typing import Callable, Any, TypeVar, ParamSpec
from collections import OrderedDict

import polars as pl

# Type hints
P = ParamSpec('P')
T = TypeVar('T')

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "out" / "cache"
DEFAULT_TTL_HOURS = 24
DEFAULT_MEMORY_ITEMS = 128


class SmartCache:
    """
    Hybrid cache: memory (LRU) + disk with TTL.

    Usage:
        cache = SmartCache(name="prices", ttl_hours=12)

        @cache.memoize
        def expensive_query(year, scenario):
            return load_data(...)
    """

    def __init__(
        self,
        name: str = "default",
        ttl_hours: float = DEFAULT_TTL_HOURS,
        memory_maxsize: int = DEFAULT_MEMORY_ITEMS,
        disk_enabled: bool = True,
        max_disk_mb: float = 500.0,  # 500 MB default
    ):
        self.name = name
        self.ttl_seconds = ttl_hours * 3600
        self.memory_maxsize = memory_maxsize
        self.disk_enabled = disk_enabled
        self.max_disk_bytes = max_disk_mb * 1024 * 1024

        # In-memory cache (thread-safe OrderedDict for LRU)
        self._memory: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

        # Disk cache directory
        self._disk_dir = CACHE_DIR / name
        if disk_enabled:
            self._disk_dir.mkdir(parents=True, exist_ok=True)

        # Stats
        self._hits_memory = 0
        self._hits_disk = 0
        self._misses = 0

    def _make_key(self, *args, **kwargs) -> str:
        """Generate a unique hash key for the arguments."""
        # Serialize arguments deterministically
        key_data = {
            "args": [self._serialize_arg(a) for a in args],
            "kwargs": {k: self._serialize_arg(v) for k, v in sorted(kwargs.items())},
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    def _serialize_arg(self, arg: Any) -> Any:
        """Serialize an argument for hashing."""
        if isinstance(arg, (list, tuple)):
            return [self._serialize_arg(x) for x in arg]
        if isinstance(arg, dict):
            return {k: self._serialize_arg(v) for k, v in sorted(arg.items())}
        if isinstance(arg, pl.DataFrame):
            return f"df_{arg.shape}_{arg.columns}"
        if isinstance(arg, Path):
            return str(arg)
        return arg

    def _is_expired(self, timestamp: float) -> bool:
        """Check if a timestamp has expired."""
        return (time.time() - timestamp) > self.ttl_seconds

    def _disk_path(self, key: str) -> Path:
        """Path to the disk cache file."""
        return self._disk_dir / f"{key}.arrow"

    def _disk_meta_path(self, key: str) -> Path:
        """Path to the metadata file."""
        return self._disk_dir / f"{key}.meta"

    def get(self, key: str) -> tuple[bool, Any]:
        """
        Get a value from cache.

        Returns:
            (found, value) - found is True if found and not expired
        """
        # 1. Search in memory
        with self._lock:
            if key in self._memory:
                ts, value = self._memory[key]
                if not self._is_expired(ts):
                    # Move to end (LRU)
                    self._memory.move_to_end(key)
                    self._hits_memory += 1
                    return True, value
                else:
                    # Expired, remove
                    del self._memory[key]

        # 2. Search on disk
        if self.disk_enabled:
            disk_file = self._disk_path(key)
            meta_file = self._disk_meta_path(key)

            if disk_file.exists() and meta_file.exists():
                try:
                    # Read metadata
                    with open(meta_file, "r") as f:
                        meta = json.load(f)

                    if not self._is_expired(meta.get("timestamp", 0)):
                        # Read DataFrame
                        value = pl.read_ipc(disk_file)

                        # Promote to memory
                        self._set_memory(key, value)
                        self._hits_disk += 1
                        return True, value
                    else:
                        # Expired, clean up
                        disk_file.unlink(missing_ok=True)
                        meta_file.unlink(missing_ok=True)
                except Exception:
                    pass

        self._misses += 1
        return False, None

    def _set_memory(self, key: str, value: Any) -> None:
        """Save in memory with LRU eviction."""
        with self._lock:
            # If already exists, update and move to end
            if key in self._memory:
                self._memory[key] = (time.time(), value)
                self._memory.move_to_end(key)
                return

            # Eviction if full
            while len(self._memory) >= self.memory_maxsize:
                self._memory.popitem(last=False)  # Remove oldest

            self._memory[key] = (time.time(), value)

    def set(self, key: str, value: Any) -> None:
        """Save a value in cache (memory + disk)."""
        # Save in memory
        self._set_memory(key, value)

        # Save to disk if DataFrame
        if self.disk_enabled and isinstance(value, pl.DataFrame):
            try:
                disk_file = self._disk_path(key)
                meta_file = self._disk_meta_path(key)

                # Write DataFrame with compression
                value.write_ipc(disk_file, compression="lz4")

                # Write metadata
                with open(meta_file, "w") as f:
                    json.dump({
                        "timestamp": time.time(),
                        "rows": value.height,
                        "cols": len(value.columns),
                    }, f)
            except Exception:
                pass  # Fail silently

        self._cleanup_disk_if_needed()

    def _cleanup_disk_if_needed(self):
        """Remove oldest files until under disk limit."""
        if not self.disk_enabled or self.max_disk_bytes <= 0:
            return

        files = sorted(
            [f for f in self._disk_dir.glob("*.arrow") if f.is_file()],
            key=lambda f: f.stat().st_mtime
        )
        total = sum(f.stat().st_size for f in files)

        while total > self.max_disk_bytes and files:
            oldest = files.pop(0)
            try:
                total -= oldest.stat().st_size
                oldest.unlink()
                self._disk_meta_path(oldest.stem).unlink(missing_ok=True)
            except OSError:
                pass

    def memoize(self, func: Callable[P, T]) -> Callable[P, T]:
        """
        Decorator to cache function results.

        Usage:
            @cache.memoize
            def expensive_query(year, scenario):
                ...
        """
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            key = self._make_key(func.__name__, *args, **kwargs)

            found, value = self.get(key)
            if found:
                return value

            # Compute and cache
            result = func(*args, **kwargs)

            if result is not None:
                self.set(key, result)

            return result

        return wrapper

    def invalidate(self, key: str | None = None) -> int:
        """
        Invalidate cache.

        Args:
            key: If None, invalidates the entire cache.

        Returns:
            Number of items invalidated.
        """
        count = 0

        with self._lock:
            if key is None:
                # Invalidate all
                count = len(self._memory)
                self._memory.clear()

                if self.disk_enabled:
                    for f in self._disk_dir.glob("*.arrow"):
                        f.unlink(missing_ok=True)
                        count += 1
                    for f in self._disk_dir.glob("*.meta"):
                        f.unlink(missing_ok=True)
            else:
                # Invalidate specific
                if key in self._memory:
                    del self._memory[key]
                    count += 1

                if self.disk_enabled:
                    self._disk_path(key).unlink(missing_ok=True)
                    self._disk_meta_path(key).unlink(missing_ok=True)

        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        total_hits = self._hits_memory + self._hits_disk
        total_requests = total_hits + self._misses
        hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0

        disk_files = list(self._disk_dir.glob("*.arrow")) if self.disk_enabled else []
        disk_size_mb = sum(f.stat().st_size for f in disk_files) / (1024 * 1024)

        return {
            "name": self.name,
            "memory_items": len(self._memory),
            "memory_maxsize": self.memory_maxsize,
            "disk_items": len(disk_files),
            "disk_size_mb": round(disk_size_mb, 2),
            "hits_memory": self._hits_memory,
            "hits_disk": self._hits_disk,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
            "ttl_hours": self.ttl_seconds / 3600,
        }

    def __repr__(self) -> str:
        stats = self.stats()
        return (
            f"SmartCache(name={self.name!r}, "
            f"memory={stats['memory_items']}/{stats['memory_maxsize']}, "
            f"disk={stats['disk_items']} files/{stats['disk_size_mb']}MB, "
            f"hit_rate={stats['hit_rate_pct']}%)"
        )


# ============================================================
# Pre-configured global caches for the dashboard
# ============================================================

# Main cache for price queries
prices_cache = SmartCache(
    name="prices",
    ttl_hours=24,
    memory_maxsize=128,
    disk_enabled=True,
)

# Cache for geographic data (smaller, long TTL)
geo_cache = SmartCache(
    name="geo",
    ttl_hours=168,  # 1 week
    memory_maxsize=32,
    disk_enabled=True,
)

# Cache for KPI calculations (more volatile)
kpi_cache = SmartCache(
    name="kpis",
    ttl_hours=1,
    memory_maxsize=256,
    disk_enabled=False,  # Memory only for KPIs
)


# ============================================================
# Convenience decorator
# ============================================================

def cached(
    cache: SmartCache | None = None,
    ttl_hours: float | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Cache decorator with options.

    Usage:
        @cached()  # Uses prices_cache by default
        def load_data(...):
            ...

        @cached(cache=geo_cache)
        def load_coordinates(...):
            ...

        @cached(ttl_hours=0.5)  # 30-minute cache
        def volatile_query(...):
            ...
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Determine which cache to use
        _cache = cache or prices_cache

        # If different TTL specified, create temporary cache
        if ttl_hours is not None and ttl_hours != _cache.ttl_seconds / 3600:
            _cache = SmartCache(
                name=f"{func.__name__}_custom",
                ttl_hours=ttl_hours,
                memory_maxsize=64,
                disk_enabled=True,
            )

        return _cache.memoize(func)

    return decorator


# ============================================================
# Utilities
# ============================================================

def clear_all_caches() -> dict:
    """Clear all global caches."""
    return {
        "prices": prices_cache.invalidate(),
        "geo": geo_cache.invalidate(),
        "kpis": kpi_cache.invalidate(),
    }


def cache_stats() -> dict:
    """Return statistics for all caches."""
    return {
        "prices": prices_cache.stats(),
        "geo": geo_cache.stats(),
        "kpis": kpi_cache.stats(),
    }


__all__ = [
    "SmartCache",
    "prices_cache",
    "geo_cache",
    "kpi_cache",
    "cached",
    "clear_all_caches",
    "cache_stats",
]
