"""Space-Track.org API client for bulk TLE catalog retrieval.

Uses cookie-based session authentication against Space-Track's ajaxauth endpoint.
Rate-limited to one fetch per 10 minutes. Gracefully degrades to empty results
on any failure (network, auth, parse).
"""

from __future__ import annotations

import logging
import os
import time
import threading

import requests

from core.tle_parser import TLEData, parse_tle_text

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.space-track.org/ajaxauth/login"
_LOGOUT_URL = "https://www.space-track.org/ajaxauth/logout"
_GP_QUERY_URL = (
    "https://www.space-track.org/basicspacedata/query"
    "/class/gp/EPOCH/>now-3/OBJECT_TYPE/PAYLOAD"
    "/orderby/NORAD_CAT_ID/format/3le"
)

_MIN_FETCH_INTERVAL_S = 600  # 10 minutes


class SpaceTrackClient:
    """Thread-safe Space-Track.org API client."""

    def __init__(self):
        self._user: str = os.environ.get("SPACETRACK_USER", "")
        self._password: str = os.environ.get("SPACETRACK_PASS", "")
        self._lock = threading.Lock()
        self._last_fetch_time: float = 0.0

    def is_configured(self) -> bool:
        return bool(self._user and self._password)

    def fetch_catalog(self) -> list[TLEData]:
        """Fetch bulk GP catalog from Space-Track.

        Returns parsed TLEData list, or empty list on any failure.
        Rate-limited: returns empty if called within 10 minutes of last fetch.
        """
        if not self.is_configured():
            logger.debug("Space-Track not configured (missing credentials)")
            return []

        with self._lock:
            now = time.monotonic()
            if now - self._last_fetch_time < _MIN_FETCH_INTERVAL_S:
                elapsed = now - self._last_fetch_time
                logger.info(
                    "Space-Track rate limit: %.0fs since last fetch (need %ds)",
                    elapsed,
                    _MIN_FETCH_INTERVAL_S,
                )
                return []

        session = requests.Session()
        try:
            logger.info("Space-Track: logging in...")
            login_resp = session.post(
                _LOGIN_URL,
                data={"identity": self._user, "password": self._password},
                timeout=30,
            )
            login_resp.raise_for_status()

            if "failed" in login_resp.text.lower():
                logger.warning("Space-Track login failed: %s", login_resp.text[:200])
                return []

            logger.info("Space-Track: fetching GP catalog...")
            data_resp = session.get(_GP_QUERY_URL, timeout=120)
            data_resp.raise_for_status()

            tle_text = data_resp.text
            if not tle_text or len(tle_text.strip()) < 100:
                logger.warning(
                    "Space-Track returned empty/short response (%d bytes)",
                    len(tle_text),
                )
                return []

            tles = parse_tle_text(tle_text)
            logger.info("Space-Track: parsed %d TLEs", len(tles))

            with self._lock:
                self._last_fetch_time = time.monotonic()

            return tles

        except requests.exceptions.Timeout:
            logger.warning("Space-Track request timed out")
            return []
        except requests.exceptions.ConnectionError as e:
            logger.warning("Space-Track connection error: %s", e)
            return []
        except requests.exceptions.HTTPError as e:
            logger.warning("Space-Track HTTP error: %s", e)
            return []
        except Exception as e:
            logger.error("Space-Track unexpected error: %s", e)
            return []
        finally:
            try:
                session.post(_LOGOUT_URL, timeout=10)
            except Exception:
                pass
            session.close()


spacetrack_client = SpaceTrackClient()
