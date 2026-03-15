from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/Sao_Paulo"


def get_tz(tz_name: str | None = None) -> ZoneInfo:
    return ZoneInfo(tz_name or DEFAULT_TZ)


def today_bounds_utc(tz_name: str | None = None) -> tuple[datetime, datetime]:
    tz = get_tz(tz_name)
    now_local = datetime.now(tz)
    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = datetime.combine(now_local.date(), time.max, tzinfo=tz)
    return start_local, end_local


def week_bounds_utc(tz_name: str | None = None, days: int = 7) -> tuple[datetime, datetime]:
    tz = get_tz(tz_name)
    now_local = datetime.now(tz)
    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = datetime.combine(now_local.date() + timedelta(days=days), time.max, tzinfo=tz)
    return start_local, end_local


def parse_datetime_local(text: str, tz_name: str | None = None) -> datetime:
    tz = get_tz(tz_name)
    text = text.strip().lower()

    if text == "hoje":
        now = datetime.now(tz)
        return datetime.combine(now.date(), time(9, 0), tzinfo=tz)

    if text in ("amanhã", "amanha"):
        now = datetime.now(tz)
        return datetime.combine(now.date() + timedelta(days=1), time(9, 0), tzinfo=tz)

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M"):
        try:
            dt = datetime.strptime(text.strip(), fmt)
            return dt.replace(tzinfo=tz)
        except ValueError:
            continue

    try:
        dt = datetime.strptime(text.strip(), "%Y-%m-%d")
        return datetime.combine(dt.date(), time(9, 0), tzinfo=tz)
    except ValueError:
        pass

    raise ValueError(
        f"Formato de data não reconhecido: '{text}'. "
        "Use YYYY-MM-DD HH:MM (ex: 2026-03-16 09:00)"
    )
