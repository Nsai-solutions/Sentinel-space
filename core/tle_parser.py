"""TLE (Two-Line Element) data parsing and management.

Parses standard TLE format into structured dataclasses,
validates checksums, manages caching, and provides access
to curated satellite groups via Celestrak.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from utils.constants import CELESTRAK_GROUPS, SECONDS_PER_DAY
from utils.downloader import DownloadResult, DownloadStatus, Downloader
from utils.time_utils import tle_epoch_to_datetime

logger = logging.getLogger(__name__)


class TLEParseError(Exception):
    """Raised when TLE data cannot be parsed."""

    def __init__(self, message: str, line_number: int = 0, raw_line: str = ""):
        self.line_number = line_number
        self.raw_line = raw_line
        super().__init__(message)


class TLEChecksumError(TLEParseError):
    """Raised when a TLE line fails checksum validation."""


@dataclass(frozen=True, slots=True)
class TLEData:
    """Parsed Two-Line Element set."""

    name: str
    catalog_number: int
    classification: str
    international_designator: str
    epoch_year: int
    epoch_day: float
    epoch_datetime: datetime
    mean_motion_dot: float
    mean_motion_ddot: float
    bstar: float
    inclination: float  # degrees
    raan: float  # degrees
    eccentricity: float
    arg_perigee: float  # degrees
    mean_anomaly: float  # degrees
    mean_motion: float  # rev/day
    revolution_number: int
    element_set_number: int
    ephemeris_type: int
    line1: str = field(repr=False)
    line2: str = field(repr=False)

    @property
    def launch_year(self) -> int:
        yr_str = self.international_designator[:2]
        try:
            yr = int(yr_str)
        except ValueError:
            return 0
        return yr + 2000 if yr < 57 else yr + 1900

    @property
    def launch_number(self) -> int:
        try:
            return int(self.international_designator[2:5])
        except (ValueError, IndexError):
            return 0

    @property
    def orbital_period_seconds(self) -> float:
        """Orbital period in seconds from mean motion."""
        if self.mean_motion <= 0:
            return float("inf")
        return SECONDS_PER_DAY / self.mean_motion

    @property
    def tle_age_days(self) -> float:
        """Age of TLE data in days from now."""
        now = datetime.now(timezone.utc)
        return (now - self.epoch_datetime).total_seconds() / SECONDS_PER_DAY


@dataclass
class TLECacheEntry:
    """Metadata for a cached TLE file."""

    group_key: str
    file_path: Path
    fetched_at: datetime
    tle_count: int

    @property
    def is_expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.fetched_at).total_seconds()
        return age > SECONDS_PER_DAY


def validate_checksum(line: str) -> bool:
    """Validate TLE line checksum (last digit)."""
    if len(line) < 69:
        return False
    checksum = 0
    for ch in line[:68]:
        if ch.isdigit():
            checksum += int(ch)
        elif ch == "-":
            checksum += 1
    return (checksum % 10) == int(line[68])


def _parse_modified_exponent(field_str: str) -> float:
    """Parse TLE modified exponential notation.

    Examples: ' 00000-0' -> 0.0, ' 38792-4' -> 3.8792e-5, '-11606-4' -> -1.1606e-5
    """
    s = field_str.strip()
    if not s or s == "0" or all(c in "0 +-" for c in s):
        return 0.0

    # Determine sign
    sign = 1.0
    if s[0] == "-":
        sign = -1.0
        s = s[1:]
    elif s[0] == "+":
        s = s[1:]

    # Find the exponent separator (last occurrence of + or -)
    exp_pos = -1
    for i in range(len(s) - 1, 0, -1):
        if s[i] in "+-":
            exp_pos = i
            break

    if exp_pos == -1:
        # No exponent found
        try:
            return sign * float("0." + s)
        except ValueError:
            return 0.0

    mantissa_str = s[:exp_pos]
    exp_str = s[exp_pos:]

    try:
        mantissa = float("0." + mantissa_str)
        exponent = int(exp_str)
        return sign * mantissa * (10.0 ** exponent)
    except ValueError:
        return 0.0


def parse_tle_lines(name: str, line1: str, line2: str) -> TLEData:
    """Parse a single TLE set from its three lines."""
    name = name.strip()
    line1 = line1.strip()
    line2 = line2.strip()

    if len(line1) < 69:
        raise TLEParseError(f"Line 1 too short ({len(line1)} chars)", 1, line1)
    if len(line2) < 69:
        raise TLEParseError(f"Line 2 too short ({len(line2)} chars)", 2, line2)

    if not validate_checksum(line1):
        logger.warning("Line 1 checksum failed for %s", name)
    if not validate_checksum(line2):
        logger.warning("Line 2 checksum failed for %s", name)

    try:
        catalog_number = int(line1[2:7].strip())
        classification = line1[7].strip() or "U"
        intl_designator = line1[9:17].strip()

        epoch_year = int(line1[18:20].strip())
        epoch_day = float(line1[20:32].strip())
        epoch_dt = tle_epoch_to_datetime(epoch_year, epoch_day)

        # Mean motion first derivative (rev/day^2 / 2)
        mm_dot_str = line1[33:43].strip()
        mean_motion_dot = float(mm_dot_str) if mm_dot_str else 0.0

        # Mean motion second derivative (modified exponent)
        mean_motion_ddot = _parse_modified_exponent(line1[44:52])

        # BSTAR drag term (modified exponent)
        bstar = _parse_modified_exponent(line1[53:61])

        ephemeris_type = int(line1[62].strip()) if line1[62].strip() else 0
        element_set_number = int(line1[64:68].strip()) if line1[64:68].strip() else 0

        # Line 2 fields
        inclination = float(line2[8:16].strip())
        raan = float(line2[17:25].strip())

        # Eccentricity has implied leading decimal point
        ecc_str = line2[26:33].strip()
        eccentricity = float("0." + ecc_str)

        arg_perigee = float(line2[34:42].strip())
        mean_anomaly = float(line2[43:51].strip())
        mean_motion = float(line2[52:63].strip())

        rev_str = line2[63:68].strip()
        revolution_number = int(rev_str) if rev_str else 0

    except (ValueError, IndexError) as e:
        raise TLEParseError(f"Failed to parse TLE for {name}: {e}") from e

    return TLEData(
        name=name,
        catalog_number=catalog_number,
        classification=classification,
        international_designator=intl_designator,
        epoch_year=epoch_year,
        epoch_day=epoch_day,
        epoch_datetime=epoch_dt,
        mean_motion_dot=mean_motion_dot,
        mean_motion_ddot=mean_motion_ddot,
        bstar=bstar,
        inclination=inclination,
        raan=raan,
        eccentricity=eccentricity,
        arg_perigee=arg_perigee,
        mean_anomaly=mean_anomaly,
        mean_motion=mean_motion,
        revolution_number=revolution_number,
        element_set_number=element_set_number,
        ephemeris_type=ephemeris_type,
        line1=line1,
        line2=line2,
    )


def parse_tle_text(text: str) -> list[TLEData]:
    """Parse all TLEs from a text string.

    Handles both 2-line format (no name) and 3-line format (name + 2 lines).
    """
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    results: list[TLEData] = []
    i = 0

    while i < len(lines):
        # Detect if current line is a TLE line 1
        if lines[i].startswith("1 ") and len(lines[i]) >= 69:
            # 2-line format (no name)
            if i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                try:
                    cat_num = lines[i][2:7].strip()
                    tle = parse_tle_lines(f"SAT-{cat_num}", lines[i], lines[i + 1])
                    results.append(tle)
                except TLEParseError as e:
                    logger.warning("Skipping bad TLE at line %d: %s", i, e)
                i += 2
            else:
                i += 1
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            # 3-line format (name + line1 + line2)
            try:
                tle = parse_tle_lines(lines[i], lines[i + 1], lines[i + 2])
                results.append(tle)
            except TLEParseError as e:
                logger.warning("Skipping bad TLE at line %d: %s", i, e)
            i += 3
        else:
            i += 1

    return results


class TLEManager:
    """Manages TLE loading, parsing, and caching."""

    def __init__(self, data_dir: Path, downloader: Optional[Downloader] = None):
        self._data_dir = data_dir
        self._downloader = downloader or Downloader(data_dir)
        self._cache_dir = data_dir / "tle_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_meta: dict[str, TLECacheEntry] = {}
        self._load_cache_metadata()

    def load_from_file(self, filepath: Path) -> list[TLEData]:
        """Parse all TLEs from a local file."""
        logger.info("Loading TLEs from file: %s", filepath)
        try:
            text = filepath.read_text(encoding="utf-8")
            return parse_tle_text(text)
        except Exception as e:
            logger.error("Failed to read TLE file %s: %s", filepath, e)
            return []

    def load_from_celestrak_group(
        self,
        group_display_name: str,
        force_refresh: bool = False,
    ) -> list[TLEData]:
        """Load a curated satellite group with caching."""
        celestrak_key = CELESTRAK_GROUPS.get(group_display_name, group_display_name)

        # Check cache
        if not force_refresh and celestrak_key in self._cache_meta:
            entry = self._cache_meta[celestrak_key]
            if not entry.is_expired and entry.file_path.exists():
                logger.info("Using cached TLEs for %s", group_display_name)
                return self.load_from_file(entry.file_path)

        # Download fresh data
        result = self._downloader.download_tle_group(celestrak_key)
        if result.status == DownloadStatus.COMPLETE and result.path:
            tles = self.load_from_file(result.path)
            self._write_cache_metadata(celestrak_key, result.path, len(tles))
            return tles

        # Fall back to expired cache
        if celestrak_key in self._cache_meta:
            entry = self._cache_meta[celestrak_key]
            if entry.file_path.exists():
                logger.warning(
                    "Download failed for %s, using expired cache", group_display_name
                )
                return self.load_from_file(entry.file_path)

        logger.warning("No TLE data available for group: %s", group_display_name)
        return []

    def load_sample_tles(self) -> list[TLEData]:
        """Load bundled sample TLEs from data/sample_tles.txt."""
        sample_path = self._data_dir / "sample_tles.txt"
        if sample_path.exists():
            return self.load_from_file(sample_path)
        # Try relative to package
        alt_path = Path(__file__).parent.parent / "data" / "sample_tles.txt"
        if alt_path.exists():
            return self.load_from_file(alt_path)
        logger.error("Sample TLE file not found")
        return []

    def load_from_norad_id(self, norad_id: int) -> Optional[TLEData]:
        """Fetch and parse a single satellite by NORAD ID."""
        result = self._downloader.download_tle_by_norad_id(norad_id)
        if result.status == DownloadStatus.COMPLETE and result.path:
            tles = self.load_from_file(result.path)
            return tles[0] if tles else None
        return None

    def search_by_name(self, query: str) -> list[TLEData]:
        """Search Celestrak by satellite name."""
        result = self._downloader.download_tle_by_name(query)
        if result.status == DownloadStatus.COMPLETE and result.path:
            return self.load_from_file(result.path)
        return []

    def get_available_groups(self) -> dict[str, str]:
        """Return the curated groups dict (display name -> Celestrak key)."""
        return dict(CELESTRAK_GROUPS)

    def _load_cache_metadata(self) -> None:
        """Scan cache directory and build metadata index."""
        for meta_file in self._cache_dir.glob("*.meta"):
            try:
                data = json.loads(meta_file.read_text())
                group_key = meta_file.stem
                tle_path = self._cache_dir / f"{group_key}.tle"
                self._cache_meta[group_key] = TLECacheEntry(
                    group_key=group_key,
                    file_path=tle_path,
                    fetched_at=datetime.fromisoformat(data["fetched_at"]),
                    tle_count=data.get("tle_count", 0),
                )
            except Exception as e:
                logger.warning("Failed to load cache metadata %s: %s", meta_file, e)

    def _write_cache_metadata(
        self, group_key: str, file_path: Path, tle_count: int
    ) -> None:
        """Write metadata JSON alongside the cached TLE file."""
        meta_path = self._cache_dir / f"{group_key}.meta"
        now = datetime.now(timezone.utc)
        data = {
            "fetched_at": now.isoformat(),
            "tle_count": tle_count,
        }
        try:
            meta_path.write_text(json.dumps(data))
            self._cache_meta[group_key] = TLECacheEntry(
                group_key=group_key,
                file_path=file_path,
                fetched_at=now,
                tle_count=tle_count,
            )
        except Exception as e:
            logger.warning("Failed to write cache metadata: %s", e)
