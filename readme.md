# 💇‍♀️ Sunny Receptionist — AI Salon Booking App

An AI-powered, tool-using receptionist for a neighborhood salon. Sunny chats with customers, answers hour/price questions, checks availability, and books appointments into JSON-backed files — all with a clear, safe conversation loop.

> **Tech**: Streamlit • OpenAI Chat Completions • Function tools • LangSmith tracing (optional) • JSON data sources

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Data Files](#data-files)
- [Validation & Normalization](#validation--normalization)
- [Setup](#setup)
- [Run Locally](#run-locally)
- [Admin Dashboard](#admin-dashboard)
- [Conversation Flow](#conversation-flow)
- [LangSmith Tracing](#langsmith-tracing)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

- **Conversational Receptionist.** Friendly, concise chat that’s easy for non‑native speakers.
- **Deterministic Conversation Loop.** Collects in order → service → date → start time → name/phone/email → confirm & book.
- **Accurate Hours & Availability.** Reads `working_hours.json` (+ `exceptions`) and removes conflicts using `calendar.json`.
- **Reliable Booking.** Re‑checks availability and writes a time block to `calendar.json`; stores contact details in `bookings.json`.
- **Contact Hygiene.** Phone normalized to **E.164** (e.g., `+13365551212`), emails lowercased and validated with a pragmatic regex.
- **Natural Dates & Dayparts.** Understands phrases like “tomorrow afternoon,” “next Tue,” `MM/DD`, `YYYY-MM-DD`.
- **Owner Admin Panel.** JSON editors with validate/save/download for each file.
- **Optional Tracing.** LangSmith integration to inspect tool calls and model reasoning steps (via a hidden planning tool).

---

## Architecture

**UI:** Streamlit chat + sidebar admin

**Model:** OpenAI Chat Completions with tool calling

\*\*Core tools (functions):

- `get_business_info` — from `business_info.json`
- `get_services` — from `services.json`
- `get_now` — current time in salon timezone
- `get_hours` — opening/closing for a date (weekly + exceptions)
- `check_availability` — free start times (slot expansion – collisions – filters)
- `book_appointment` — re-check + write to `calendar.json` and append to `bookings.json`
- `get_conversation_state` / `update_conversation_state` — slot state in session
- `normalize_and_store_date` — normalize natural date → `YYYY-MM-DD`
- `internal_plan` — **hidden** planning tool (not shown to the user)

**Slot Expansion Logic:**

1. Expand daily opening ranges into start slots at `slot_interval_minutes` (default 15).
2. Ensure a full service duration fits before closing.
3. Subtract collisions found in `calendar.json` (e.g., `10:00-10:30`).
4. Filter by **daypart** if requested (e.g., afternoon 12:00–16:59).
5. If date is today, remove any slot whose end time is in the past.

---

## Data Files

The app seeds files if missing. All paths are configurable via env vars.

### `business_info.json` (no hours/services here)

```json
{
  "Business Name": "Your Salon",
  "Address": "",
  "Phone": "",
  "Email": "",
  "Timezone": "America/New_York",
  "Policies": {},
  "Announcements": []
}
```

### `services.json`

```json
{
  "services": [
    {"name": "Basic Haircut", "duration": 30, "price": 30, "description": "A classic cut and simple styling."},
    {"name": "Skin Fade", "duration": 45, "price": 45, "description": "Tight fade with clean transitions."},
    {"name": "Beard Trim", "duration": 20, "price": 20, "description": "Shape and trim with line cleanup."}
  ]
}
```

### `working_hours.json`

```json
{
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
  "exceptions": {
    "2025-12-25": [],
    "2025-12-31": ["09:00-13:00"]
  }
}
```

### `calendar.json`

```json
{
  "appointments": {
    "2025-10-18": ["10:00-10:30", "11:30-12:00"]
  }
}
```

### `bookings.json`

```json
{
  "bookings": [
    {
      "date": "2025-10-18",
      "start": "10:00",
      "end": "10:30",
      "service": "Basic Haircut",
      "duration_minutes": 30,
      "client": {"name": "Jane Doe", "phone": "+13365551212", "email": "jane@example.com"},
      "created_at": "2025-10-17T20:10:00-04:00"
    }
  ]
}
```

---

## Validation & Normalization

- **Phone:** accepted format is strictly **E.164**, e.g., `+13365551212`.
  - US inputs without `+1` (10 or 11 digits) are auto-normalized to E.164 when possible.
- **Email:** lowercased and validated with a robust regex (no leading/trailing dot in local part; domain requires TLD 2–63 chars).
- **Time:** flexible inputs (`9`, `9:00`, `1:30 pm`, `13`, `13:45`) normalized to `HH:MM` 24‑hour.
- **Date:** `YYYY-MM-DD`, `MM/DD`, weekday names, `today`/`tomorrow`, and `next Tue` supported; dayparts recognized.

---

## Setup

1. **Python 3.9+** (requires `zoneinfo`).
2. Install deps:
   ```bash
   pip install streamlit openai>=1.40 python-dotenv
   # optional for tracing
   pip install langsmith
   ```
3. Create a `.env` (or use Streamlit secrets) with:
   ```bash
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o-mini
   ADMIN_USERNAME=owner
   ADMIN_PASSWORD=changeme

   # Optional: LangSmith
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=lsv2_...
   LANGCHAIN_PROJECT=Sunny Receptionist
   # LANGSMITH_ENDPOINT=https://api.smith.langchain.com  # optional override
   ```

**Configurable file paths** (optional):

```bash
BUSINESS_INFO_FILE=business_info.json
SERVICES_FILE=services.json
WORKING_HOURS_FILE=working_hours.json
CALENDAR_FILE=calendar.json
BOOKINGS_FILE=bookings.json
```

---

## Run Locally

```bash
streamlit run app.py
```

Open the URL shown (usually [http://localhost:8501](http://localhost:8501)). The app seeds missing JSON files with sensible defaults.

---

## Admin Dashboard

Open the **Owner/Admin** section in the sidebar, sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

- **Business Info:** Edit basic store metadata.
- **Services:** Define names, durations (minutes), and prices.
- **Hours & Dates:** Configure weekly hours, slot interval, and date-specific exceptions.
- **Calendar:** Inspect/modify time blocks per date (`"HH:MM-HH:MM"`).
- **Bookings:** Read‑only table of bookings with client contact (downloadable).

> After saving JSON files, the app clears caches. You can click **Reload** if needed.

---

## Conversation Flow

1. **User intent → Service** (Sunny may list services with bullets.)
2. **Date** (accepts natural phrases; internally normalized to `YYYY-MM-DD`).
3. **Time** (offers 3–8 options; excludes collisions and past‑ending slots).
4. **Contact** (name, E.164 phone, email).
5. **Confirm & Book** (writes to `calendar.json` and `bookings.json`).
6. **Receipt** (summarizes service, date, time, duration, price if known).

**Examples**

- “What time do you close tomorrow?” → `get_hours("tomorrow")`
- “Basic Haircut tomorrow afternoon” → `check_availability` with daypart → collect contact → `book_appointment`.

---

## LangSmith Tracing

**Public example trace:** [https://smith.langchain.com/public/3e9e2377-7f2d-4dca-9fb0-92bf45056b63/r](https://smith.langchain.com/public/3e9e2377-7f2d-4dca-9fb0-92bf45056b63/r)

**Enable tracing:**

1. `pip install langsmith`
2. Set in `.env`:
   ```bash
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=lsv2_...
   LANGCHAIN_PROJECT=Sunny Receptionist
   ```
3. Run the app and chat. You’ll see runs (including tool calls) appear under the project.

**Notes:**

- Tracing is gated behind `HAS_LANGSMITH` and `LANGCHAIN_TRACING_V2=true`.
- If you don’t see runs, confirm the API key and ensure the package is installed in the same environment where Streamlit runs.

---

## Troubleshooting

**Hours seem wrong**

- Check `working_hours.json` **timezone** and the app’s `business_info.json` `Timezone`.
- Remember: `exceptions` override weekly hours for specific dates.

**“That start time isn’t available.”**

- The slot may have been taken between offering and booking.
- The **service duration** must fully fit before closing.
- For **today**, slots whose **end time** is in the past are filtered out.

**Model not responding / API error**

- Verify `OPENAI_API_KEY` and `OPENAI_MODEL`.
- Reduce chat history length (the app already bounds to 30 turns).

**No LangSmith runs**

- Ensure `pip show langsmith` works in the same interpreter.
- Confirm `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY`.

**Cache gotchas**

- The app uses `st.cache_data`. After saving JSON, cache is cleared.
- Use **Reload** in Admin panel if the UI looks stale.

---

## Security Notes

- **PII scope:** Only **name, phone, email** per booking — stored in `bookings.json`.
- **Minimal retention:** Booking entries include an ISO timestamp; consider external rotation if needed.
- **Admin auth:** Simple username/password gate — set strong secrets in production.
- **Validation:** Strict E.164 phones; pragmatic email regex; times normalized to 24h; dates normalized to `YYYY-MM-DD`.

---

## Roadmap

- Service‑specific buffers and cleanup times.
- Staff calendars / multi‑chair support.
- ICS email confirmations (MCP + Zapier action).
- Holiday import & bulk exception editing.
- Unit tests for slot math and validators.

---

## License

MIT © 2025

