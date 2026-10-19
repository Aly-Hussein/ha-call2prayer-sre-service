import re
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")


@dataclass(frozen=True)
class DailySchedule:
    date: str
    hijri_date: str
    fajr_azan: str
    fajr_iqama: str
    shurooq: str
    zuhr_azan: str
    zuhr_iqama: str
    asr_azan: str
    asr_iqama: str
    maghrib_azan: str
    maghrib_iqama: str
    isha_azan: str
    isha_iqama: str
    jumah_1: str
    jumah_2: str
    cache_status: str = "FRESH"

    def to_dict(self) -> dict:
        return asdict(self)


def _to_iso(date_str: str, hhmm: str) -> str:
    """Converts YYYYMMDD and HHMM into an ISO-8601 timestamp for Home Assistant."""
    dt = datetime.strptime(f"{date_str}{hhmm}", "%Y%m%d%H%M").replace(tzinfo=TZ)
    return dt.isoformat()


def extract_mpt_dict(html: str) -> dict[str, str]:
    """Extracts the (MousquePrayerTime) MPT={...} dictionary from raw HTML."""
    match = re.search(r"MPT\s*=\s*\{([^}]+)\}", html)
    if not match:
        raise ValueError("MPT dictionary not found in HTML payload")

    entries = re.findall(r'(\d{8})\s*:\s*"(\d{56,60})"', match.group(1))
    if not entries:
        raise ValueError("No valid 56/60-char prayer strings found in MPT object")

    return dict(entries)


def parse_day_string(date_str: str, raw: str, cache_status: str = "FRESH") -> DailySchedule:
    """Slices the 56 or 60-character numeric string into ISO-8601 timestamps."""
    if len(raw) not in (56, 60) or not raw.isdigit():
        raise ValueError(f"Invalid MPT string format for {date_str}: {raw}")

    return DailySchedule(
        date=date_str,
        hijri_date=f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}",
        fajr_azan=_to_iso(date_str, raw[8:12]),
        fajr_iqama=_to_iso(date_str, raw[12:16]),
        shurooq=_to_iso(date_str, raw[16:20]),
        zuhr_azan=_to_iso(date_str, raw[20:24]),
        zuhr_iqama=_to_iso(date_str, raw[24:28]),
        asr_azan=_to_iso(date_str, raw[28:32]),
        asr_iqama=_to_iso(date_str, raw[32:36]),
        maghrib_azan=_to_iso(date_str, raw[36:40]),
        maghrib_iqama=_to_iso(date_str, raw[40:44]),
        isha_azan=_to_iso(date_str, raw[44:48]),
        isha_iqama=_to_iso(date_str, raw[48:52]),
        jumah_1=_to_iso(date_str, raw[52:56]),
        jumah_2=_to_iso(date_str, raw[56:60]) if len(raw) == 60 else _to_iso(date_str, raw[52:56]),
        cache_status=cache_status,
    )