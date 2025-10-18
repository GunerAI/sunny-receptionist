#!/usr/bin/env python3
# streamlit run app.py
import os
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv

try:
    from openai import OpenAI
except Exception as e:
    st.error("OpenAI SDK not found. Install with: pip install openai>=1.40 python-dotenv")
    raise

try:
    from zoneinfo import ZoneInfo
except Exception:
    st.error("Python 3.9+ with zoneinfo is required.")
    raise

# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL: LangSmith tracing (safe shim if not installed)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from langsmith import traceable, Client as LangsmithClient
    HAS_LANGSMITH = True
except Exception:
    HAS_LANGSMITH = False
    def traceable(*targs, **tkwargs):
        def deco(fn):
            return fn
        return deco
    LangsmithClient = None

# ─────────────────────────────────────────────────────────────────────────────
# Page config (early so Streamlit applies layout/theme right away)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Sunny Receptionist", page_icon="💇‍♀️", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# Config & Secrets
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()  # allow local .env for dev

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)
MODEL = os.getenv("OPENAI_MODEL") or st.secrets.get("OPENAI_MODEL", "gpt-5-chat-latest")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME") or st.secrets.get("ADMIN_USERNAME", "owner")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or st.secrets.get("ADMIN_PASSWORD", "changeme")

BUSINESS_FILE = os.getenv("BUSINESS_INFO_FILE") or "business_info.json"
SERVICES_FILE = os.getenv("SERVICES_FILE") or "services.json"
WORKING_FILE = os.getenv("WORKING_HOURS_FILE") or "working_hours.json"
CALENDAR_FILE = os.getenv("CALENDAR_FILE") or "calendar.json"  # holds existing appointments
BOOKINGS_FILE = os.getenv("BOOKINGS_FILE") or "bookings.json"  # contact info records

if not OPENAI_API_KEY:
    st.error("❌ Missing OPENAI_API_KEY. Set it as an environment variable or in .streamlit/secrets.toml")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# LangSmith env handling
# ─────────────────────────────────────────────────────────────────────────────
def _get_secret(key: str, env_name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(env_name)
    if v not in (None, ""):
        return v
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

LANGCHAIN_TRACING_V2 = _get_secret("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING_V2", "false")
LANGCHAIN_API_KEY     = _get_secret("LANGCHAIN_API_KEY", "LANGCHAIN_API_KEY", None)
LANGCHAIN_PROJECT     = _get_secret("LANGCHAIN_PROJECT", "LANGCHAIN_PROJECT", "Sunny Receptionist")
LANGSMITH_ENDPOINT    = _get_secret("LANGSMITH_ENDPOINT", "LANGSMITH_ENDPOINT", None)

if HAS_LANGSMITH and (LANGCHAIN_TRACING_V2 or "").lower() == "true" and LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    if LANGCHAIN_PROJECT:
        os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT
    if LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = LANGSMITH_ENDPOINT
    LS_CLIENT = LangsmithClient()
else:
    LS_CLIENT = None

# ─────────────────────────────────────────────────────────────────────────────
# System prompt (Sunny) — includes conversation loop directive
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are “Sunny,” a friendly, quick, and helpful AI receptionist for a neighborhood hair salon.

## Goals
- Greet warmly and keep it short, upbeat, and clear.
- Use the provided tools for facts & actions. Never invent details.
- Follow a conversation loop (state machine): collect in order → service → date → start time → client name/phone/email → confirm & book.

## Tools
- `get_business_info` → business details (name, address, phone, email, timezone, policies, announcements).
- `get_services` → services with price/duration (from services.json).
- `get_now` → current date/time in salon timezone.
- `get_hours` → opening/closing hours for a given date (from working_hours.json + exceptions).
- `check_availability` → ALWAYS before answering availability or booking; uses working_hours.json + calendar.json.
- `book_appointment` → AFTER user confirms date/time & shares contact; re-checks then writes to files.
- `get_conversation_state` / `update_conversation_state` → read/update dialog slots (service, date, time, name, phone, email).
- `internal_plan` → hidden planning scratchpad. Use it to outline steps; do not reveal to user.

## Tone & Style
- Warm, concise, and accessible to non-native speakers.
- Use short bullets for lists (services, hours, slots).
- No code or JSON in replies unless asked.

## Conversation Rules
1) For opening/closing hours questions: call `get_hours` for the date (and `get_now` if you need to resolve “today/tomorrow”).
2) On any availability request: call `get_now` (when needed) then `check_availability`.
3) Only offer a small set of slots (3–8) and a next step.
4) When booking, summarize: service, date, time, duration, total price (if known). Collect name, phone, email. Then call `book_appointment`.
5) If a slot becomes unavailable, apologize, show new options.
6) Never store sensitive data beyond name/phone/email.

## What the local files contain
- business_info.json: Business Name, Address, Phone, Email, Timezone, Policies, Announcements. (🚫 No working hours or services here.)
- services.json: Services list with name, duration (minutes), price, description.
- working_hours.json: Scheduler config — timezone, slot_interval_minutes, weekly_hours, exceptions.
- calendar.json: Booked appointments per date: { "YYYY-MM-DD": ["HH:MM-HH:MM", ...] }.
- bookings.json: Client contact records for each booking (name, phone, email), separate from calendar.

## Output
- Plain text. Short paragraphs. Bulleted lists for options.
- No mention of internal planning or tools to the user.
""".strip()

# Hidden controller that nudges multi-step reasoning via an internal planning tool
REASONING_CONTROLLER = """
You have a hidden tool called `internal_plan` for deliberate planning.
For EACH user message:
- First, CALL `internal_plan` once with a compact JSON plan:
  { "objective": "...", "steps": ["..."], "missing_info": ["..."], "tools_to_use": ["..."], "state_updates": { ... } }
- Then execute the plan using other tools (`get_services`, `get_hours`, `check_availability`, `update_conversation_state`, etc.).
- Finally, produce a short, user-facing reply (no mention of planning or tools).
- Keep collecting state in order: service → date → time → name/phone/email → confirm.
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# Files: seed/ensure/load
# ─────────────────────────────────────────────────────────────────────────────
def _write_json(path: str, payload: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

def ensure_business_file(path: str):
    """Seed WITHOUT working hours or services."""
    if not os.path.exists(path):
        seed = {
            "Business Name": "Your Salon",
            "Address": "",
            "Phone": "",
            "Email": "",
            "Timezone": "America/New_York",
            "Policies": {},
            "Announcements": []
        }
        _write_json(path, seed)

def ensure_services_file(path: str):
    if not os.path.exists(path):
        seed_services = {
            "services": [
                {"name": "Basic Haircut", "duration": 30, "price": 30.0, "description": "A classic cut and simple styling."},
                {"name": "Skin Fade", "duration": 45, "price": 45.0, "description": "Tight fade with clean transitions."},
                {"name": "Beard Trim", "duration": 20, "price": 20.0, "description": "Shape and trim with line cleanup."}
            ]
        }
        _write_json(path, seed_services)

def ensure_working_file(path: str):
    if not os.path.exists(path):
        seed_working = {
            "timezone": "America/New_York",
            "slot_interval_minutes": 15,
            "weekly_hours": {
                "Mon": ["09:00-17:00"],
                "Tue": ["09:00-17:00"],
                "Wed": ["09:00-17:00"],
                "Thu": ["09:00-17:00"],
                "Fri": ["09:00-17:00"],
                "Sat": ["10:00-14:00"],
                "Sun": []
            },
            "exceptions": {}
        }
        _write_json(path, seed_working)

def ensure_calendar_file(path: str):
    if not os.path.exists(path):
        seed_calendar = {"appointments": {}}
        _write_json(path, seed_calendar)

def ensure_bookings_file(path: str):
    if not os.path.exists(path):
        _write_json(path, {"bookings": []})

@st.cache_data
def load_business_info_cached(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_services_cached(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_working_cached(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_calendar_cached(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_bookings_cached(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_business_info(path: str) -> Dict[str, Any]:
    try:
        ensure_business_file(path)
        return load_business_info_cached(path)
    except Exception:
        return {}

def load_services(path: str) -> Dict[str, Any]:
    try:
        ensure_services_file(path)
        return load_services_cached(path)
    except Exception:
        return {"services": []}

def load_working(path: str) -> Dict[str, Any]:
    try:
        ensure_working_file(path)
        return load_working_cached(path)
    except Exception:
        return {}

def load_calendar(path: str) -> Dict[str, Any]:
    try:
        ensure_calendar_file(path)
        return load_calendar_cached(path)
    except Exception:
        return {"appointments": {}}

def load_bookings(path: str) -> Dict[str, Any]:
    try:
        ensure_bookings_file(path)
        return load_bookings_cached(path)
    except Exception:
        return {"bookings": []}

def _save_calendar(cal: Dict[str, Any]) -> None:
    try:
        with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
            json.dump(cal, f, indent=2, ensure_ascii=False)
        st.cache_data.clear()
    except Exception as e:
        raise RuntimeError(f"Failed to save calendar: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Utility: time helpers
# ─────────────────────────────────────────────────────────────────────────────
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Dayparts to allow phrases like "tomorrow afternoon"
DAYPARTS = {
    "morning": ("00:00", "11:59"),
    "afternoon": ("12:00", "16:59"),
    "evening": ("17:00", "20:59"),
    "night": ("21:00", "23:59")
}

def extract_daypart(s: str) -> Tuple[str, Optional[Tuple[str,str]]]:
    s = (s or "").strip().lower()
    for k, rng in DAYPARTS.items():
        if k in s:
            clean = s.replace(k, "").strip()
            return clean, rng
    return s, None

def _salon_tz() -> ZoneInfo:
    biz = load_business_info(BUSINESS_FILE)
    wh = load_working(WORKING_FILE)
    tz = (wh.get("timezone") or biz.get("Timezone") or "America/New_York")
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("America/New_York")

def now_in_salon_tz() -> datetime:
    return datetime.now(_salon_tz())

def parse_natural_date(phrase: str, anchor: datetime) -> Optional[datetime]:
    s = (phrase or "").strip().lower()
    if not s:
        return None

    # ISO yyyy-mm-dd
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            y, m, d = s.split("-")
            return anchor.replace(year=int(y), month=int(m), day=int(d), hour=0, minute=0, second=0, microsecond=0)
    except Exception:
        pass

    # MM/DD
    try:
        if "/" in s:
            m, d = s.split("/")
            year = anchor.year
            return anchor.replace(year=year, month=int(m), day=int(d), hour=0, minute=0, second=0, microsecond=0)
    except Exception:
        pass

    if s in ("today", "todays", "to day"):
        return anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    if s in ("tomorrow", "tmrw", "tmr"):
        return (anchor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    def _weekday_index(name: str) -> Optional[int]:
        name = name[:3].capitalize()
        if name in WEEKDAY_NAMES:
            return WEEKDAY_NAMES.index(name)
        return None

    toks = s.split()
    if len(toks) == 1:
        day_idx = _weekday_index(toks[0])
        if day_idx is not None:
            delta = (day_idx - anchor.weekday()) % 7
            return (anchor + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)

    if len(toks) == 2 and toks[0] == "next":
        day_idx = _weekday_index(toks[1])
        if day_idx is not None:
            delta = ((day_idx - anchor.weekday()) % 7) or 7
            return (anchor + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)

    return None

def _time_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h)*60 + int(m)

def _minutes_to_time(m: int) -> str:
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"

def _expand_ranges_to_slots(ranges: List[str], slot_interval: int, service_min: int) -> List[str]:
    slots: List[str] = []
    for r in ranges:
        try:
            start_s, end_s = r.split("-")
            start = _time_to_minutes(start_s)
            end = _time_to_minutes(end_s)
            t = start
            while t + service_min <= end:
                slots.append(_minutes_to_time(t))
                t += slot_interval
        except Exception:
            continue
    return slots

def _subtract_appointments(slots: List[str], taken_ranges: List[str], service_min: int) -> List[str]:
    keep: List[str] = []
    for s in slots:
        start = _time_to_minutes(s)
        end = start + service_min
        conflict = False
        for r in taken_ranges or []:
            try:
                rs, re = r.split("-")
                rs_m = _time_to_minutes(rs)
                re_m = _time_to_minutes(re)
                if start < re_m and end > rs_m:
                    conflict = True
                    break
            except Exception:
                continue
        if not conflict:
            keep.append(s)
    return keep

def _get_service_minutes(name: Optional[str]) -> int:
    data = load_services(SERVICES_FILE)
    services = data.get("services", [])
    if name:
        for s in services:
            if str(s.get("name","")).lower() == name.strip().lower():
                dur = s.get("duration", 30)
                try:
                    return int(dur)
                except Exception:
                    pass
    return 30

def _normalize_time_to_hhmm(s: str) -> Optional[str]:
    """
    Accept common inputs: '9', '09', '9:00', '9.00', '9 00', '9am', '1:30 pm', '13', '13:45'.
    Returns 'HH:MM' or None.
    """
    if not s:
        return None
    t = s.strip().lower().replace(".", ":").replace(" ", "")
    ampm = None
    if t.endswith("am") or t.endswith("pm"):
        ampm = t[-2:]
        t = t[:-2]

    if t.isdigit():
        h = int(t)
        m = 0
    else:
        if ":" in t:
            parts = t.split(":")
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                return None
            h = int(parts[0]); m = int(parts[1])
        else:
            return None

    if ampm:
        if ampm == "am":
            if h == 12:  # 12am -> 00
                h = 0
        else:  # pm
            if h != 12:
                h += 12

    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"

# ─────────────────────────────────────────────────────────────────────────────
# Booking helpers
# ─────────────────────────────────────────────────────────────────────────────
def _append_booking_record(date_str: str, start_hhmm: str, end_hhmm: str,
                           service_name: Optional[str], duration_min: int,
                           client_name: str, phone: str, email: str) -> None:
    ensure_bookings_file(BOOKINGS_FILE)
    data = load_bookings(BOOKINGS_FILE)
    rec = {
        "date": date_str,
        "start": start_hhmm,
        "end": end_hhmm,
        "service": service_name,
        "duration_minutes": int(duration_min),
        "client": {"name": client_name, "phone": phone, "email": email},
        "created_at": now_in_salon_tz().isoformat()
    }
    data.setdefault("bookings", []).append(rec)
    with open(BOOKINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    st.cache_data.clear()

def _get_taken_ranges_from_calendar(date_str: str) -> List[str]:
    cal = load_calendar(CALENDAR_FILE)
    appts = cal.get("appointments", {})
    return appts.get(date_str, []) or []

def _append_appointment(date_str: str, start_hhmm: str, duration_min: int,
                        client_name: str, phone: str, email: str) -> Tuple[bool, str]:
    """
    Only writes to calendar.json (no bookings write here).
    """
    try:
        _ = _time_to_minutes(start_hhmm)
    except Exception:
        return False, "Invalid start time format. Use HH:MM."

    end_minutes = _time_to_minutes(start_hhmm) + int(duration_min)
    end_hhmm = _minutes_to_time(end_minutes)

    # Collision check
    taken = _get_taken_ranges_from_calendar(date_str)
    start_m = _time_to_minutes(start_hhmm)
    end_m = end_minutes
    for r in taken:
        try:
            rs, re = r.split("-")
            rs_m = _time_to_minutes(rs)
            re_m = _time_to_minutes(re)
            if start_m < re_m and end_m > rs_m:
                return False, "That time was just taken. Please pick another slot."
        except Exception:
            continue

    # Append
    cal = load_calendar(CALENDAR_FILE)
    cal.setdefault("appointments", {})
    cal["appointments"].setdefault(date_str, [])
    new_range = f"{start_hhmm}-{end_hhmm}"
    if new_range not in cal["appointments"][date_str]:
        cal["appointments"][date_str].append(new_range)

    # Sort by start
    def _sort_key(rr: str) -> int:
        try:
            ss, _ee = rr.split("-")
            return _time_to_minutes(ss)
        except Exception:
            return 0
    cal["appointments"][date_str] = sorted(list(set(cal["appointments"][date_str])), key=_sort_key)
    _save_calendar(cal)

    return True, f"Booked {date_str} {start_hhmm}-{end_hhmm}."

# ─────────────────────────────────────────────────────────────────────────────
# NEW: Hours helper tool
# ─────────────────────────────────────────────────────────────────────────────
@traceable(name="tool:get_hours")
def get_hours(date_phrase: Optional[str] = None) -> Dict[str, Any]:
    """
    Return opening/closing time windows for a given date, respecting weekly_hours and exceptions.
    Example:
    {
      "date": "2025-10-18",
      "weekday": "Sat",
      "ranges": ["10:00-14:00"],
      "opening": "10:00",
      "closing": "14:00",
      "closed": False
    }
    """
    working = load_working(WORKING_FILE)
    anchor = now_in_salon_tz()
    date_dt = parse_natural_date(date_phrase or "today", anchor)
    if not date_dt:
        return {"error": "Could not parse date.", "date": None, "closed": None}

    date_str = date_dt.strftime("%Y-%m-%d")
    weekday = WEEKDAY_NAMES[date_dt.weekday()]
    weekly_hours: Dict[str, List[str]] = working.get("weekly_hours", {})
    exceptions: Dict[str, List[str]] = working.get("exceptions", {})

    ranges = exceptions.get(date_str, weekly_hours.get(weekday, [])) or []
    if not ranges:
        return {"date": date_str, "weekday": weekday, "ranges": [], "opening": None, "closing": None, "closed": True}

    try:
        starts = []
        ends = []
        for r in ranges:
            s, e = r.split("-")
            starts.append(s.strip())
            ends.append(e.strip())
        opening = sorted(starts, key=_time_to_minutes)[0]
        closing = sorted(ends, key=_time_to_minutes)[-1]
    except Exception:
        opening, closing = None, None

    return {
        "date": date_str,
        "weekday": weekday,
        "ranges": ranges,
        "opening": opening,
        "closing": closing,
        "closed": False
    }

# ─────────────────────────────────────────────────────────────────────────────
# Tools: business/services/now/hours/availability/booking + conversation-state + internal plan
# ─────────────────────────────────────────────────────────────────────────────
@traceable(name="tool:get_business_info")
def get_business_info(keys: List[str]) -> Dict[str, Any]:
    data = load_business_info(BUSINESS_FILE)
    found: Dict[str, Any] = {}
    missing: List[str] = []
    for k in keys:
        if k in data and data[k] not in (None, "", []):
            found[k] = data[k]
        else:
            missing.append(k)
    return {"data": found, "missing": missing}

@traceable(name="tool:get_services")
def get_services(names: Optional[List[str]] = None) -> Dict[str, Any]:
    data = load_services(SERVICES_FILE)
    services = data.get("services", [])
    if names:
        name_set = {n.strip().lower() for n in names if isinstance(n, str)}
        filtered = [s for s in services if str(s.get("name", "")).lower() in name_set]
        missing = [n for n in names if n.strip().lower() not in {str(s.get("name","")).lower() for s in services}]
        return {"services": filtered, "missing": missing}
    return {"services": services, "missing": []}

@traceable(name="tool:get_now")
def get_now() -> Dict[str, Any]:
    now = now_in_salon_tz()
    return {
        "timezone": str(_salon_tz().key),
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "weekday": WEEKDAY_NAMES[now.weekday()]
    }

@traceable(name="tool:check_availability")
def check_availability(date_phrase: Optional[str] = None,
                       service_name: Optional[str] = None,
                       limit: int = 8,
                       daypart: Optional[Tuple[str,str]] = None) -> Dict[str, Any]:
    working = load_working(WORKING_FILE)

    # NEW: peel off daypart if embedded in the phrase (e.g., "tomorrow afternoon")
    cleaned_phrase, embedded_daypart = extract_daypart(date_phrase or "")
    if embedded_daypart and not daypart:
        daypart = embedded_daypart

    anchor = now_in_salon_tz()
    date_dt = parse_natural_date(cleaned_phrase or "today", anchor)
    if not date_dt:
        return {"error": "Could not parse date.", "available": [], "date": None}

    date_str = date_dt.strftime("%Y-%m-%d")
    weekday = WEEKDAY_NAMES[date_dt.weekday()]
    weekly_hours: Dict[str, List[str]] = working.get("weekly_hours", {})
    exceptions: Dict[str, List[str]] = working.get("exceptions", {})
    slot_interval = int(working.get("slot_interval_minutes", 15))

    ranges = weekly_hours.get(weekday, [])
    if date_str in exceptions:
        ranges = exceptions.get(date_str, [])

    if not ranges:
        return {"date": date_str, "weekday": weekday, "available": [], "closed": True}

    service_min = _get_service_minutes(service_name)
    all_slots = _expand_ranges_to_slots(ranges, slot_interval, service_min)

    # Apply calendar conflicts
    taken_ranges = _get_taken_ranges_from_calendar(date_str)
    free_slots = _subtract_appointments(all_slots, taken_ranges, service_min)

    # daypart filter (use start >= start_m and start < end_m - duration)
    if daypart:
        start_m = _time_to_minutes(daypart[0])
        end_m = _time_to_minutes(daypart[1])
        free_slots = [
            s for s in free_slots
            if _time_to_minutes(s) >= start_m
            and _time_to_minutes(s) + service_min <= end_m
        ]

    # today filter (slot end must be in the future)
    now_local = now_in_salon_tz()
    if date_str == now_local.strftime("%Y-%m-%d"):
        now_m = _time_to_minutes(now_local.strftime("%H:%M"))
        free_slots = [s for s in free_slots if _time_to_minutes(s) + service_min > now_m]

    return {
        "date": date_str,
        "weekday": weekday,
        "service": service_name,
        "duration_minutes": service_min,
        "available": free_slots[:max(1, int(limit))],
        "total_available": len(free_slots),
    }

@traceable(name="tool:book_appointment")
def book_appointment(date_str: str,
                     start_time: str,
                     service_name: Optional[str],
                     client_name: str,
                     phone: str,
                     email: str) -> Dict[str, Any]:
    # normalize date_str if it contains a daypart word
    cleaned_date, _ = extract_daypart(date_str)
    date_str = cleaned_date or date_str

    start_time_norm = _normalize_time_to_hhmm(start_time)
    if not start_time_norm:
        return {"success": False, "error": "Please enter time as HH:MM (e.g., 09:00 or 1:30 pm)."}

    duration_min = _get_service_minutes(service_name)
    avail = check_availability(date_phrase=date_str, service_name=service_name, limit=10000)
    if avail.get("closed"):
        return {"success": False, "error": "The salon is closed that day."}

    free_slots = avail.get("available", [])
    if start_time_norm not in free_slots:
        return {
            "success": False,
            "error": "That start time isn’t available.",
            "alternatives": free_slots[:10],
            "date": avail.get("date"),
            "service": service_name,
            "duration_minutes": duration_min
        }

    ok, msg = _append_appointment(avail["date"], start_time_norm, duration_min,
                                  client_name, phone, email)
    if not ok:
        fresh = check_availability(date_phrase=avail["date"], service_name=service_name, limit=8)
        return {
            "success": False,
            "error": msg,
            "alternatives": fresh.get("available", []),
            "date": avail["date"],
            "service": service_name,
            "duration_minutes": duration_min
        }

    end_time = _minutes_to_time(_time_to_minutes(start_time_norm) + duration_min)
    _append_booking_record(avail["date"], start_time_norm, end_time, service_name, duration_min,
                           client_name, phone, email)
    return {
        "success": True,
        "message": "Your appointment is confirmed!",
        "date": avail["date"],
        "start_time": start_time_norm,
        "end_time": end_time,
        "service": service_name,
        "duration_minutes": duration_min,
        "client_name": client_name
    }

# Conversation state stored in session (not visible to user)
def _ensure_dialogue_container():
    if "dialogue" not in st.session_state:
        st.session_state.dialogue = {
            "service": None,
            "date": None,    # YYYY-MM-DD or phrase
            "time": None,    # HH:MM
            "name": None,
            "phone": None,
            "email": None,
            "confirmed": False
        }

@traceable(name="tool:get_conversation_state")
def get_conversation_state() -> Dict[str, Any]:
    _ensure_dialogue_container()
    return {"state": st.session_state.dialogue}

@traceable(name="tool:update_conversation_state")
def update_conversation_state(**kwargs) -> Dict[str, Any]:
    _ensure_dialogue_container()
    allowed = {"service", "date", "time", "name", "phone", "email", "confirmed"}

    # If a date is provided, normalize it immediately (avoid recursion)
    if "date" in kwargs and kwargs["date"]:
        try:
            normalize_and_store_date(str(kwargs["date"]))
            kwargs = {k: v for k, v in kwargs.items() if k != "date"}
        except Exception:
            pass

    for k, v in kwargs.items():
        if k in allowed:
            st.session_state.dialogue[k] = v
    return {"state": st.session_state.dialogue}

@traceable(name="tool:normalize_and_store_date")
def normalize_and_store_date(date_phrase: str):
    """
    Normalize a natural date phrase and write directly to session state to avoid recursion.
    """
    _ensure_dialogue_container()
    cleaned, _dp = extract_daypart(date_phrase)
    dt = parse_natural_date(cleaned, now_in_salon_tz())
    if dt:
        st.session_state.dialogue["date"] = dt.strftime("%Y-%m-%d")
        return {"ok": True, "date": dt.strftime("%Y-%m-%d")}
    else:
        st.session_state.dialogue["date"] = cleaned
        return {"ok": True, "date": cleaned, "normalized": False}

# ── Tool list (includes internal planning + conv-state tools) ────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "internal_plan",
            "description": "Hidden planning tool. Use FIRST each turn to outline objective, steps, missing info, and tools. Do NOT expose to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "missing_info": {"type": "array", "items": {"type": "string"}},
                    "tools_to_use": {"type": "array", "items": {"type": "string"}},
                    "state_updates": {"type": "object"}
                },
                "required": ["objective"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_business_info",
            "description": "Read specific fields from business_info.json and return values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to fetch, e.g., ['Business Name','Address','Phone','Policies','Announcements','Timezone','Email']"
                    }
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_services",
            "description": "Return services (optionally filtered by name) with name, duration, price, and description from services.json.",
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of service names to filter; exact (case-insensitive) name match."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_now",
            "description": "Return the current date/time in the salon timezone as ISO string and friendly parts.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hours",
            "description": "Return opening/closing hours for a given date, respecting weekly_hours and exceptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_phrase": {"type": "string", "description": "Natural date phrase or explicit date (e.g., 'tomorrow', '2025-10-18')."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Compute available start times for a given date phrase considering weekly_hours, exceptions, and the calendar of existing appointments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_phrase": {"type": "string", "description": "Natural date phrase or explicit date."},
                    "service_name": {"type": "string", "description": "Optional service name to determine duration."},
                    "limit": {"type": "integer", "description": "Max number of slots to return (default 8)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment by re-checking availability and then saving the time range to calendar.json.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Booking date in 'YYYY-MM-DD' (or natural phrase previously resolved)."},
                    "start_time": {"type": "string", "description": "Start time in HH:MM (24h)."},
                    "service_name": {"type": "string", "description": "Service name to determine duration."},
                    "client_name": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"}
                },
                "required": ["date_str", "start_time", "client_name", "phone", "email"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_conversation_state",
            "description": "Return the current conversation slot state (service, date, time, name, phone, email, confirmed).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "normalize_and_store_date",
            "description": "Normalize a natural date phrase (e.g., 'tomorrow afternoon') and store YYYY-MM-DD into conversation state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_phrase": {"type": "string"}
                },
                "required": ["date_phrase"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_conversation_state",
            "description": "Update conversation slot state with any provided keys (service, date, time, name, phone, email, confirmed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "confirmed": {"type": "boolean"}
                }
            }
        }
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# Admin Dashboard (Owner)
# ─────────────────────────────────────────────────────────────────────────────
def _json_editor(title: str, path: str, loader_fn, height: int = 420, key_prefix: str = ""):
    kp = key_prefix or os.path.basename(path).replace(".", "_")

    st.caption(f"Editing file: `{path}`")
    current = loader_fn(path)
    pretty = json.dumps(current or {}, indent=2, ensure_ascii=False)

    st.markdown(f"**{title}**")
    edited = st.text_area(
        label=title,
        value=pretty,
        height=height,
        help="Edit JSON then click Validate → Save to apply.",
        key=f"{kp}_textarea",
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])

    with c1:
        if st.button("Validate JSON", use_container_width=True, key=f"{kp}_validate"):
            try:
                json.loads(edited)
                st.success("JSON is valid ✅")
            except Exception as e:
                st.error(f"Invalid JSON: {e}")

    with c2:
        if st.button("Save", type="primary", use_container_width=True, key=f"{kp}_save"):
            try:
                parsed = json.loads(edited)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(parsed, f, indent=2, ensure_ascii=False)
                st.cache_data.clear()
                st.success("Saved changes.")
            except Exception as e:
                st.error(f"Save failed: {e}")

    with c3:
        if st.button("Reload", use_container_width=True, key=f"{kp}_reload"):
            st.cache_data.clear()
            st.rerun()

    with c4:
        dl = json.dumps(loader_fn(path), indent=2, ensure_ascii=False)
        st.download_button(
            label="Download current JSON",
            file_name=os.path.basename(path),
            mime="application/json",
            data=dl.encode("utf-8"),
            use_container_width=True,
            key=f"{kp}_download",
        )

def admin_panel():
    st.subheader("Admin Settings")
    if "admin_authed" not in st.session_state:
        st.session_state.admin_authed = False

    if not st.session_state.admin_authed:
        with st.form("admin_login_form", clear_on_submit=False):
            u = st.text_input("Username", value="", type="default", key="admin_username_input")
            p = st.text_input("Password", value="", type="password", key="admin_password_input")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
            if submitted:
                if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
                    st.session_state.admin_authed = True
                    st.success("Signed in.")
                else:
                    st.error("Invalid credentials.")
        return

    # Ensure files exist before editing
    ensure_business_file(BUSINESS_FILE)
    ensure_services_file(SERVICES_FILE)
    ensure_working_file(WORKING_FILE)
    ensure_calendar_file(CALENDAR_FILE)
    ensure_bookings_file(BOOKINGS_FILE)

    # Tabs
    t1, t2, t3, t4, t5 = st.tabs(["🏪 Business Info", "💈 Services", "🗓 Hours & Dates", "📅 Calendar", "👤 Bookings"])
    with t1:
        st.markdown(
            "_business_info.json_ fields only:\n\n"
            "- **Business Name**\n"
            "- **Address**\n"
            "- **Phone**\n"
            "- **Email**\n"
            "- **Timezone**\n"
            "- **Policies** (object)\n"
            "- **Announcements** (array)\n\n"
            "⚠️ Working hours and services live in their own files."
        )
        _json_editor("business_info.json", BUSINESS_FILE, load_business_info, key_prefix="business_info")

    with t2:
        st.markdown(
            "Define services in **services.json** like:\n\n"
            "```json\n"
            "{\n"
            "  \"services\": [\n"
            "    {\"name\": \"Basic Haircut\", \"duration\": 30, \"price\": 30, \"description\": \"A classic cut.\"}\n"
            "  ]\n"
            "}\n"
            "```"
        )
        _json_editor("services.json", SERVICES_FILE, load_services, key_prefix="services_file")

    with t3:
        st.markdown(
            "Scheduling source of truth (**working_hours.json**):\n\n"
            "- `timezone`: e.g., `America/New_York`\n"
            "- `slot_interval_minutes`: e.g., `15`\n"
            "- `weekly_hours`: e.g., `\"Mon\": [\"09:00-17:00\"]`\n"
            "- `exceptions`: date-specific overrides (empty list = closed)\n\n"
            "❗ Existing appointments are stored in **Calendar**, not here."
        )
        _json_editor("working_hours.json", WORKING_FILE, load_working, key_prefix="working_file")

    with t4:
        st.markdown(
            "Appointment blocks in **calendar.json**:\n"
            "```json\n"
            "{\n"
            "  \"appointments\": {\n"
            "    \"YYYY-MM-DD\": [\"HH:MM-HH:MM\", \"HH:MM-HH:MM\"]\n"
            "  }\n"
            "}\n"
            "```\n"
            "_Client details live in bookings.json for privacy._"
        )
        _json_editor("calendar.json", CALENDAR_FILE, load_calendar, key_prefix="calendar_file")

    with t5:
        st.markdown("Read-only viewer of client bookings.")
        bookings = load_bookings(BOOKINGS_FILE).get("bookings", [])
        st.dataframe(bookings, use_container_width=True, hide_index=True)
        st.download_button(
            "Download bookings.json",
            data=json.dumps({"bookings": bookings}, indent=2, ensure_ascii=False).encode("utf-8"),
            file_name="bookings.json",
            mime="application/json",
            use_container_width=True,
            key="bookings_download_btn"
        )

    st.divider()
    st.caption("Tip: Set ADMIN_USERNAME / ADMIN_PASSWORD via environment variables or Streamlit secrets.")
    # LangSmith status hint
    if HAS_LANGSMITH and os.getenv("LANGCHAIN_TRACING_V2") == "true":
        st.caption(f"🧭 LangSmith tracing: ON (project: {os.getenv('LANGCHAIN_PROJECT','default')})")
    elif not HAS_LANGSMITH:
        st.caption("🧭 LangSmith tracing: package not installed (pip install langsmith)")

# ─────────────────────────────────────────────────────────────────────────────
# LLM wrapper (traced)
# ─────────────────────────────────────────────────────────────────────────────
@traceable(name="openai.chat.completions.create")
def _llm_call(model: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], temperature: float = 0.6):
    return client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
    )

# (Optional) wrap a user turn
@traceable(name="ui:handle_user_turn")
def _handle_user_turn_run(messages_payload: List[Dict[str, Any]]):
    return _llm_call(model=MODEL, messages=messages_payload, tools=TOOLS, temperature=0.6)

# ─────────────────────────────────────────────────────────────────────────────
# UI: Chat (with conversation loop + internal planning)
# ─────────────────────────────────────────────────────────────────────────────
st.title("💇‍♀️ Sunny — Salon Receptionist")

with st.sidebar:
    st.markdown("### Owner/Admin")
    admin_panel()

# Keep message history bounded to avoid token bloat
MAX_HISTORY = 30

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": "Hi there! I’m Sunny, your friendly salon receptionist. How can I help today?"}
    ]

# Render chat history (except the system message)
for i, m in enumerate(st.session_state.messages):
    if m["role"] == "system":
        continue
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

user_text = st.chat_input("Type your message")
if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    if len(st.session_state.messages) > MAX_HISTORY:
        st.session_state.messages = [st.session_state.messages[0]] + st.session_state.messages[-(MAX_HISTORY-1):]

    with st.chat_message("user"):
        st.markdown(user_text)

    controller_hint = {"role": "system", "content": REASONING_CONTROLLER}

    try:
        # First LLM call (traced)
        response = _handle_user_turn_run([
            *[
                {"role": m["role"], "content": m.get("content",""), **({"tool_calls": m.get("tool_calls")} if "tool_calls" in m else {})}
                for m in st.session_state.messages
            ],
            controller_hint,
        ])
    except Exception as e:
        with st.chat_message("assistant"):
            st.error(f"Model error: {e}")
        st.stop()

    message = response.choices[0].message

    # Tool-iteration loop (keep a single execute_tool_call defined here)
    interim_messages = [
        *[
            {"role": m["role"], "content": m.get("content",""), **({"tool_calls": m.get("tool_calls")} if "tool_calls" in m else {})}
            for m in st.session_state.messages
        ],
        controller_hint,
    ]

    max_tool_iters = 10
    tool_iters = 0

    @traceable(name="tool:execute_tool_call")
    def execute_tool_call(tool_call) -> Dict[str, Any]:
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments or "{}")

        if name == "internal_plan":
            return {"received_plan": True, "plan": args}
        if name == "get_business_info":
            keys = args.get("keys", [])
            return get_business_info(keys)
        if name == "get_services":
            names = args.get("names")
            return get_services(names)
        if name == "get_now":
            return get_now()
        if name == "get_hours":
            return get_hours(args.get("date_phrase"))
        if name == "check_availability":
            return check_availability(
                date_phrase=args.get("date_phrase"),
                service_name=args.get("service_name"),
                limit=int(args.get("limit", 8)),
            )
        if name == "book_appointment":
            return book_appointment(
                date_str=args.get("date_str"),
                start_time=args.get("start_time"),
                service_name=args.get("service_name"),
                client_name=args.get("client_name"),
                phone=args.get("phone"),
                email=args.get("email"),
            )
        if name == "get_conversation_state":
            return get_conversation_state()
        if name == "update_conversation_state":
            return update_conversation_state(**{k: v for k, v in args.items()})
        if name == "normalize_and_store_date":
            return normalize_and_store_date(args.get("date_phrase", ""))

        return {"error": f"Unknown tool {name}"}

    while getattr(message, "tool_calls", None) and tool_iters < max_tool_iters:
        # run every tool call returned in this message
        tc_blocks = []
        tool_results = []
        for tool_call in message.tool_calls:
            payload = execute_tool_call(tool_call)
            tool_iters += 1
            tc_blocks.append({
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            })
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": json.dumps(payload, ensure_ascii=False),
            })

        interim_messages.extend([
            {"role": "assistant", "tool_calls": tc_blocks},
            *tool_results,
        ])

        follow = _llm_call(
            model=MODEL,
            messages=interim_messages,
            tools=TOOLS,
            temperature=0.6,
        )
        message = follow.choices[0].message

    assistant_text = message.content or "(no content)"

    st.session_state.messages.append({"role": "assistant", "content": assistant_text})
    with st.chat_message("assistant"):
        st.markdown(assistant_text)
