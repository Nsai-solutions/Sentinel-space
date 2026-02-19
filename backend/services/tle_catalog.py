"""TLE catalog service for full satellite catalog management.

Manages fetching, caching, and querying the full CelesTrak satellite
catalog for conjunction screening operations.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.tle_parser import TLEData, TLEManager, parse_tle_text
from utils.downloader import Downloader

logger = logging.getLogger(__name__)

# CelesTrak GP data URLs for full catalog
CATALOG_URLS = {
    "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
    "stations": "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "analyst": "https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=tle",
    "cosmos-2251-debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=tle",
    "iridium-33-debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-33-debris&FORMAT=tle",
    "fengyun-1c-debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=1999-025&FORMAT=tle",
}


class TLECatalogService:
    """Manages the full satellite/debris catalog for screening.

    Thread-safe singleton that holds the in-memory catalog and
    provides query methods.
    """

    def __init__(self):
        if os.environ.get("VERCEL"):
            self._data_dir = Path("/tmp") / "tle_data"
            self._data_dir.mkdir(parents=True, exist_ok=True)
            # Copy sample TLEs to writable dir
            src = Path(__file__).parent.parent / "data" / "sample_tles.txt"
            dst = self._data_dir / "sample_tles.txt"
            if src.exists() and not dst.exists():
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            self._data_dir = Path(__file__).parent.parent / "data"
        self._downloader = Downloader(self._data_dir)
        self._tle_manager = TLEManager(self._data_dir, self._downloader)
        self._catalog: dict[int, TLEData] = {}
        self._lock = threading.Lock()
        self._last_refresh: Optional[datetime] = None
        self._initialized = False

    def initialize(self):
        """Load initial catalog from cache or sample TLEs.

        Tries in order: disk cache > CelesTrak fetch > sample TLEs.
        """
        try:
            # Try loading cached catalog
            cache_file = self._data_dir / "tle_cache" / "full_catalog.txt"
            if cache_file.exists():
                text = cache_file.read_text(encoding="utf-8")
                if len(text.strip()) > 100:
                    tles = parse_tle_text(text)
                    with self._lock:
                        for tle in tles:
                            self._catalog[tle.catalog_number] = tle
                    logger.info("Loaded %d TLEs from cache", len(self._catalog))

            # If cache was empty/missing, try fetching from CelesTrak
            # Skip on Vercel cold start to avoid timeout — use sample TLEs instead
            if self.catalog_size < 50 and not os.environ.get("VERCEL"):
                logger.info("Catalog too small (%d), fetching from CelesTrak...", self.catalog_size)
                self._fetch_initial_catalog()

            # Final fallback: sample TLEs
            if self.catalog_size == 0:
                tles = self._tle_manager.load_sample_tles()
                with self._lock:
                    for tle in tles:
                        self._catalog[tle.catalog_number] = tle
                logger.info("Loaded %d sample TLEs as fallback catalog", len(self._catalog))

            self._initialized = True
            logger.info("Catalog initialized with %d objects", self.catalog_size)
        except Exception as e:
            logger.error("Failed to initialize catalog: %s", e)
            # Still load sample TLEs as absolute fallback
            try:
                tles = self._tle_manager.load_sample_tles()
                with self._lock:
                    for tle in tles:
                        self._catalog[tle.catalog_number] = tle
            except Exception:
                pass
            self._initialized = True

    def _fetch_initial_catalog(self):
        """Fetch key TLE groups from CelesTrak for initial catalog."""
        import requests

        priority_groups = [
            ("stations", CATALOG_URLS["stations"]),
            ("active", CATALOG_URLS["active"]),
        ]

        for group_name, url in priority_groups:
            try:
                logger.info("Fetching TLE group: %s", group_name)
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                tles = parse_tle_text(resp.text)
                self.add_tles(tles)
                logger.info("Fetched %d TLEs from %s", len(tles), group_name)

                # Save to cache
                cache_dir = self._data_dir / "tle_cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path = cache_dir / f"{group_name}.txt"
                cache_path.write_text(resp.text, encoding="utf-8")

            except Exception as e:
                logger.warning("Failed to fetch %s: %s", group_name, e)

        # Save combined catalog cache
        if self.catalog_size > 0:
            self._save_catalog_cache()

    @property
    def catalog_size(self) -> int:
        with self._lock:
            return len(self._catalog)

    def get_all_tles(self) -> list[TLEData]:
        """Return all TLEs in the catalog."""
        with self._lock:
            return list(self._catalog.values())

    def get_tle(self, norad_id: int) -> Optional[TLEData]:
        """Get a single TLE by NORAD ID."""
        with self._lock:
            return self._catalog.get(norad_id)

    def search(self, query: str) -> list[TLEData]:
        """Search catalog by name or NORAD ID."""
        with self._lock:
            if query.isdigit():
                tle = self._catalog.get(int(query))
                return [tle] if tle else []
            query_upper = query.upper()
            return [
                tle for tle in self._catalog.values()
                if query_upper in tle.name.upper()
            ]

    def add_tle(self, tle: TLEData) -> None:
        """Add or update a single TLE in the catalog."""
        with self._lock:
            self._catalog[tle.catalog_number] = tle

    def add_tles(self, tles: list[TLEData]) -> int:
        """Add multiple TLEs. Returns count added."""
        with self._lock:
            for tle in tles:
                self._catalog[tle.catalog_number] = tle
            return len(tles)

    def fetch_by_norad_id(self, norad_id: int) -> Optional[TLEData]:
        """Fetch a fresh TLE from CelesTrak by NORAD ID."""
        try:
            tle = self._tle_manager.load_from_norad_id(norad_id)
            if tle:
                self.add_tle(tle)
            return tle
        except Exception as e:
            logger.warning("Failed to fetch TLE for NORAD %d: %s", norad_id, e)
            return self.get_tle(norad_id)

    def fetch_group(self, group_name: str) -> list[TLEData]:
        """Fetch a CelesTrak group and add to catalog."""
        try:
            tles = self._tle_manager.load_from_celestrak_group(group_name, force_refresh=True)
            self.add_tles(tles)
            return tles
        except Exception as e:
            logger.warning("Failed to fetch group %s: %s", group_name, e)
            return []

    def refresh_catalog(self) -> int:
        """Refresh the full catalog from CelesTrak. Returns total count."""
        total = 0
        for group_name, url in CATALOG_URLS.items():
            try:
                result = self._downloader.download(
                    url,
                    self._data_dir / "tle_cache" / f"{group_name}.txt",
                )
                if result.path and result.path.exists():
                    text = result.path.read_text(encoding="utf-8")
                    tles = parse_tle_text(text)
                    self.add_tles(tles)
                    total += len(tles)
                    logger.info("Loaded %d TLEs from %s", len(tles), group_name)
            except Exception as e:
                logger.warning("Failed to refresh %s: %s", group_name, e)

        self._last_refresh = datetime.utcnow()
        logger.info("Catalog refresh complete: %d total objects", self.catalog_size)

        # Save full catalog to cache
        self._save_catalog_cache()
        return total

    def _save_catalog_cache(self):
        """Save current catalog to disk cache."""
        try:
            cache_file = self._data_dir / "tle_cache" / "full_catalog.txt"
            lines = []
            with self._lock:
                for tle in self._catalog.values():
                    lines.append(tle.name)
                    lines.append(tle.line1)
                    lines.append(tle.line2)
            cache_file.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save catalog cache: %s", e)

    def get_catalog_stats(self) -> dict:
        """Get statistics about the catalog."""
        with self._lock:
            total = len(self._catalog)

        return {
            "total_objects": total,
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "initialized": self._initialized,
        }


# Singleton instance
catalog_service = TLECatalogService()
