"""Thread-safe HTTP downloader for TLE data and Earth textures.

Provides downloading from Celestrak and NASA with progress callbacks,
atomic file writes, and caching support.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

import requests

from utils.constants import CELESTRAK_BASE_URL, CELESTRAK_GROUPS, NASA_BLUE_MARBLE_URL

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]  # (bytes_downloaded, total_bytes)


class DownloadStatus(Enum):
    PENDING = auto()
    DOWNLOADING = auto()
    COMPLETE = auto()
    FAILED = auto()


@dataclass
class DownloadResult:
    """Result of a download operation."""
    status: DownloadStatus
    path: Optional[Path] = None
    error: Optional[str] = None
    bytes_downloaded: int = 0


class Downloader:
    """Thread-safe file downloader with progress reporting."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._lock = threading.Lock()
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        """Lazy-init a requests.Session (reuses TCP connections)."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "OrbitalPropagator/1.0"
            })
        return self._session

    def download_tle_group(
        self,
        group_key: str,
        progress: Optional[ProgressCallback] = None,
        timeout: float = 30.0,
    ) -> DownloadResult:
        """Fetch TLE data for a satellite group from Celestrak."""
        celestrak_key = CELESTRAK_GROUPS.get(group_key, group_key)
        url = f"{CELESTRAK_BASE_URL}?GROUP={celestrak_key}&FORMAT=tle"
        dest = self._data_dir / "tle_cache" / f"{celestrak_key}.tle"
        dest.parent.mkdir(parents=True, exist_ok=True)
        return self._download_file(url, dest, progress, timeout)

    def download_tle_by_name(
        self,
        name: str,
        progress: Optional[ProgressCallback] = None,
        timeout: float = 30.0,
    ) -> DownloadResult:
        """Fetch TLE for a single satellite by name."""
        url = f"{CELESTRAK_BASE_URL}?NAME={name}&FORMAT=tle"
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        dest = self._data_dir / "tle_cache" / f"name_{safe_name}.tle"
        dest.parent.mkdir(parents=True, exist_ok=True)
        return self._download_file(url, dest, progress, timeout)

    def download_tle_by_norad_id(
        self,
        norad_id: int,
        progress: Optional[ProgressCallback] = None,
        timeout: float = 30.0,
    ) -> DownloadResult:
        """Fetch TLE by NORAD catalog number."""
        url = f"{CELESTRAK_BASE_URL}?CATNR={norad_id}&FORMAT=tle"
        dest = self._data_dir / "tle_cache" / f"norad_{norad_id}.tle"
        dest.parent.mkdir(parents=True, exist_ok=True)
        return self._download_file(url, dest, progress, timeout)

    def download_earth_texture(
        self,
        progress: Optional[ProgressCallback] = None,
        timeout: float = 120.0,
    ) -> DownloadResult:
        """Download NASA Blue Marble texture. Only downloads if not cached."""
        dest = self._data_dir / "textures" / "earth_texture.jpg"
        if dest.exists():
            logger.info("Earth texture already cached at %s", dest)
            return DownloadResult(
                status=DownloadStatus.COMPLETE,
                path=dest,
                bytes_downloaded=dest.stat().st_size,
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        return self._download_file(NASA_BLUE_MARBLE_URL, dest, progress, timeout)

    def download(
        self,
        url: str,
        dest: Path,
        progress: Optional[ProgressCallback] = None,
        timeout: float = 30.0,
    ) -> DownloadResult:
        """Download a file from URL to dest path."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        return self._download_file(url, dest, progress, timeout)

    def _download_file(
        self,
        url: str,
        dest: Path,
        progress: Optional[ProgressCallback],
        timeout: float,
    ) -> DownloadResult:
        """Core download logic with streaming and progress reporting."""
        logger.info("Downloading %s -> %s", url, dest)
        try:
            session = self._get_session()
            response = session.get(url, stream=True, timeout=timeout)
            response.raise_for_status()

            # Check for Celestrak error responses
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type and "FORMAT=tle" in url:
                # Celestrak returns HTML on errors (e.g., no results)
                text = response.text.strip()
                if not text or "<html" in text.lower():
                    return DownloadResult(
                        status=DownloadStatus.FAILED,
                        error="No TLE data found for query",
                    )

            total = int(response.headers.get("content-length", 0))
            downloaded = 0

            # Write to temp file first for atomic operation
            fd, tmp_path = tempfile.mkstemp(
                dir=str(dest.parent), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress:
                                progress(downloaded, total)

                # Atomic rename
                with self._lock:
                    tmp = Path(tmp_path)
                    if dest.exists():
                        dest.unlink()
                    tmp.rename(dest)

            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.info("Download complete: %s (%d bytes)", dest, downloaded)
            return DownloadResult(
                status=DownloadStatus.COMPLETE,
                path=dest,
                bytes_downloaded=downloaded,
            )

        except requests.exceptions.Timeout:
            msg = f"Download timed out after {timeout}s: {url}"
            logger.warning(msg)
            return DownloadResult(status=DownloadStatus.FAILED, error=msg)

        except requests.exceptions.ConnectionError as e:
            msg = f"Connection error downloading {url}: {e}"
            logger.warning(msg)
            return DownloadResult(status=DownloadStatus.FAILED, error=msg)

        except requests.exceptions.HTTPError as e:
            msg = f"HTTP error downloading {url}: {e}"
            logger.warning(msg)
            return DownloadResult(status=DownloadStatus.FAILED, error=msg)

        except Exception as e:
            msg = f"Unexpected error downloading {url}: {e}"
            logger.error(msg)
            return DownloadResult(status=DownloadStatus.FAILED, error=msg)
