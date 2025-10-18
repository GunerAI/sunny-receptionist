# Sunny Receptionist

An AI‑powered salon receptionist built with **Streamlit** and **OpenAI Chat Completions**. It handles multi‑turn booking conversations, checks working hours and existing appointments, and writes confirmed bookings to JSON for an owner dashboard.

---

## ✨ Features

- Friendly, multi‑step **conversation loop** (service → date → time → client info → confirm).
- **Tool‑calling** orchestration for: business info, services, hours, availability, booking, and conversation state.
- Timezone‑aware scheduling; supports natural dates (e.g., *tomorrow afternoon*).
- Availability computed from `working_hours.json` + **exceptions** + `calendar.json` collisions.
- **Admin dashboard** with JSON editors: Business Info, Services, Hours & Dates, Calendar, Bookings.
- **Separate data files** (business info vs. working hours vs. services), clean persistence layer.
- Optional **LangSmith** tracing (safe shim if not installed).

---

## 🗂️ Project Structure

```
.
├── app.py                   # Streamlit app (main)
├── business_info.json       # Name, address, phone, email, timezone, policies, announcements
├── services.json            # Services catalog (name, duration, price, description)
├── working_hours.json       # Timezone, slot interval, weekly hours, exceptions
├── calendar.json            # Existing appointments { "YYYY-MM-DD": ["HH:MM-HH:MM", ...] }
├── bookings.json            # Booked clients (name, phone, email) per appointment
├── .env                     # (optional, local dev) API keys and admin creds
├── .gitignore
└── README.md
```

> On first run, the app **seeds** missing JSON files with safe defaults.

---

## 🚀 Quick Start

### 1) Prerequisites

- Python **3.9+** (uses `zoneinfo`)
- `pip install -r requirements.txt` *(or)* `pip install streamlit openai python-dotenv`
- An **OpenAI API key** with access to your chosen model

### 2) Environment

Create a `.env` file (or set Streamlit *Secrets*):

```env
OPENAI_API_KEY=sk-...           # required
OPENAI_MODEL=gpt-4o-mini        # optional override
ADMIN_USERNAME=owner            # optional
ADMIN_PASSWORD=changeme         # optional
BUSINESS_INFO_FILE=business_info.json
SERVICES_FILE=services.json
WORKING_HOURS_FILE=working_hours.json
CALENDAR_FILE=calendar.json
BOOKINGS_FILE=bookings.json

# Optional: LangSmith tracing
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=Sunny Receptionist
LANGSMITH_ENDPOINT=
```

### 3) Run the app

```bash
streamlit run app.py
```

Then open the URL Streamlit prints in your terminal.

---

## ⚙️ Configuration Files

### `business_info.json` *(no hours/services here)*

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
    "2025-12-25": []
  }
}
```

### `calendar.json`

```json
{
  "appointments": {
    "2025-10-18": ["10:00-10:30", "11:00-11:45"]
  }
}
```

### `bookings.json`

```json
{
  "bookings": [
    {
      "date": "2025-10-18",
      "start": "11:00",
      "end": "11:45",
      "service": "Skin Fade",
      "duration_minutes": 45,
      "client": {"name": "Jane Doe", "phone": "+1-555-0100", "email": "jane@example.com"},
      "created_at": "2025-10-17T21:42:00-04:00"
    }
  ]
}
```

---

## 🧠 Conversation & Tools (built‑in)

- `get_business_info`, `get_services`, `get_now`, `get_hours`
- `check_availability` → expands slots from working hours + filters collisions from `calendar.json`; respects service duration, dayparts, and "today" cutoff.
- `book_appointment` → re‑checks availability and writes to `calendar.json` + `bookings.json`.
- `get_conversation_state` / `update_conversation_state` / `normalize_and_store_date`
- Hidden `internal_plan` to keep reasoning out of user replies.

---

## 🔐 Admin Dashboard

In the sidebar → **Owner/Admin** → sign in (credentials from env or defaults). Tabs:

- **🏪 Business Info** – edit `business_info.json`
- **💈 Services** – edit `services.json`
- **🗓 Hours & Dates** – edit `working_hours.json`
- **📅 Calendar** – edit `calendar.json`
- **👤 Bookings** – view/download `bookings.json`

Each editor provides **Validate**, **Save**, **Reload**, and **Download** actions.

---

## 🧪 Development Tips

- The app seeds JSON if missing. Safe to delete a file and re‑run.
- Caching: uses `@st.cache_data`. After editing files, code calls `st.cache_data.clear()` to refresh.
- Time parsing: liberal input normalization (e.g., `1:30 pm` → `13:30`).
- Date parsing: supports `YYYY-MM-DD`, `MM/DD`, weekdays, `today`, `tomorrow`, and `next <weekday>`.

---

## 🛠️ Troubleshooting

- **Missing API Key**: set `OPENAI_API_KEY` in `.env` or Streamlit **Secrets**.
- **Duplicate button ID**: give each Streamlit button a unique `key` (the app already scopes keys via prefixes per JSON file tab).
- **Model errors**: verify `OPENAI_MODEL` is available to your API key.
- **Wrong hours/availability**: check `working_hours.json` `weekly_hours` vs `exceptions`; ensure the salon timezone matches your intent.

---

## 📦 GitHub: Repo Setup & Push

Below are ready‑to‑run commands. Run them from the project root (where `app.py` lives).

### Option A — Using GitHub CLI (`gh`)

```bash
# 1) Initialize git
git init

# 2) Ignore local-only files
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/
.env

# Streamlit
.streamlit/

# OS
.DS_Store
Thumbs.db
EOF

# 3) Create a README from this document if you haven't saved it yet
# (Skip if README.md already exists)
[ -f README.md ] || printf "# Sunny Receptionist\n\nSee README in repo." > README.md

# 4) Commit
git add .
git commit -m "Initial commit: Sunny Receptionist app"

# 5) Create and push repo
gh repo create sunny-receptionist --source=. --public --remote=origin --push
```

### Option B — Using plain Git (create repo on GitHub web UI)

```bash
# 1) Initialize and commit locally
git init
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.venv/
.env
.streamlit/
.DS_Store
Thumbs.db
EOF

git add .
git commit -m "Initial commit: Sunny Receptionist app"

# 2) Create an empty repo on GitHub (e.g., https://github.com/<you>/sunny-receptionist)
# 3) Add remote and push
git branch -M main
git remote add origin https://github.com/<your-username>/sunny-receptionist.git
git push -u origin main
```

> **Tip**: If you prefer SSH remotes:
>
> ```bash
> git remote add origin git@github.com:<your-username>/sunny-receptionist.git
> git push -u origin main
> ```

---

## ☁️ Deploy (Streamlit Community Cloud)

1. Push the repo to GitHub.
2. In Streamlit Cloud → **New app** → select repo/branch and `app.py` as the entrypoint.
3. Set **Secrets**:
   - `OPENAI_API_KEY: sk-...`
   - (optional) `OPENAI_MODEL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, etc.
4. Deploy.

---

## 📄 License

Choose a license (e.g., MIT). Example `LICENSE`:

```
MIT License

Copyright (c) 2025 <Your Name>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND...
```

---

## ✅ Next Steps

- Edit `business_info.json`, `services.json`, and `working_hours.json` from the **Admin** sidebar.
- Add a `requirements.txt` (example):
  ```
  streamlit
  openai>=1.40
  python-dotenv
  langsmith
  ```
- Commit and push using one of the options above.

Happy shipping! 💇‍♀️✨

