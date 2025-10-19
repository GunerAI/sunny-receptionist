# 💇‍♀️ Sunny Receptionist

An AI-powered Streamlit app that acts as a **salon receptionist** — manages appointments, checks availability, and books customers using **OpenAI Chat Completions** with function tools.

---

## 🌟 Features

- Conversational AI receptionist powered by OpenAI (`gpt-5-chat-latest` by default)  
- Multi-step reasoning and tool calling (availability, booking, hours)  
- JSON-based local storage for business data, services, working hours, calendar, and bookings  
- Built-in **Admin Dashboard** for editing data and viewing bookings  
- Optional **LangSmith tracing** for debugging and analytics  
- Input validation for E.164 phone format and strict email regex  

---

## 🧰 Requirements

- **Python 3.10+** (with `zoneinfo` module)
- Internet connection
- OpenAI API key
- (Optional) LangSmith account for tracing

---

## ⚙️ Installation and Local Setup

### 1️⃣ Clone the repository
```bash
git clone https://github.com/GunerAI/sunny-receptionist.git
cd sunny-receptionist
```

### 2️⃣ Create and activate a virtual environment
**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell)**
```bash
python -m venv venv
venv\Scripts\activate
```

### 3️⃣ Install dependencies
```bash
pip install -r requirements.txt
```
If no `requirements.txt` exists:
```bash
pip install streamlit python-dotenv "openai>=1.40"
```

---

## 🔑 Environment Variables

You can use a `.env` file or `.streamlit/secrets.toml`.

```env
OPENAI_API_KEY = "sk-your-key"
OPENAI_MODEL = "gpt-4o-mini"
ADMIN_USERNAME = "owner"
ADMIN_PASSWORD = "changeme"

BUSINESS_INFO_FILE = "business_info.json"
SERVICES_FILE      = "services.json"
WORKING_HOURS_FILE = "working_hours.json"
CALENDAR_FILE      = "calendar.json"
BOOKINGS_FILE      = "bookings.json"
```

> ⚠️ **Change your admin password** before deploying publicly.

---

## ▶️ Run the App

```bash
streamlit run app.py
```

Then open your browser at  
👉 http://localhost:8501

---

## 🗂️ First Run — Auto JSON Seeding

On first launch, the app automatically creates starter JSON files if missing:

| File | Purpose |
|------|----------|
| `business_info.json` | Salon name, contact, timezone, policies |
| `services.json` | List of services with price/duration |
| `working_hours.json` | Weekly hours & exceptions |
| `calendar.json` | Tracks booked time ranges |
| `bookings.json` | Stores client info (name, phone, email) |

You can edit all files in **Admin Panel** on the sidebar.

---

## 🧑‍💼 Admin Dashboard

- Sign in (default):  
  **Username:** `owner`  
  **Password:** `pass1`

Tabs include:
- **🏪 Business Info** – contact details, policies  
- **💈 Services** – name, duration, price  
- **🗓 Hours & Dates** – weekly hours and exceptions  
- **📅 Calendar** – existing appointments  
- **👤 Bookings** – client records (read-only)

---

## 🧠 Example Prompts

Try chatting with Sunny:
```
What are your hours tomorrow?
I need a Basic Haircut tomorrow afternoon.
Book 1:00 pm under Alex, phone +17035550123, email alex@example.com.
```

✅ Phone must be **E.164 format** (`+1XXXXXXXXXX`)  
✅ Email must be lowercase and valid (`name@example.com`)

---

## 🧭 LangSmith Tracing (Optional)

To enable LangSmith tracing for debugging:

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY="lsm_..."
export LANGCHAIN_PROJECT="Sunny Receptionist"
```

**Public example trace:**  
👉 https://smith.langchain.com/public/3e9e2377-7f2d-4dca-9fb0-92bf45056b63/r

---

## 🧩 Troubleshooting

| Issue | Solution |
|-------|-----------|
| ❌ `Missing OPENAI_API_KEY` | Add key to `.env` or secrets |
| ⏰ `That start time isn’t available` | Check working hours or calendar |
| 📞 `Invalid phone/email` | Use correct format: `+1XXXXXXXXXX`, lowercase email |
| 🔐 `Invalid admin credentials` | Update `.env` or `.streamlit/secrets.toml` |

