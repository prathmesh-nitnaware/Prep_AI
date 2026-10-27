# 🛠️ Prep AI — Local Setup Guide

A step-by-step guide to get the full Prep AI stack running on your machine from scratch.

---

## 📋 Prerequisites

Make sure the following are installed before you begin:

| Tool | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ | Backend (Flask) |
| **Node.js** | 18+ | Frontend (Vite + React) |
| **npm** | 9+ | Frontend package manager |
| **Git** | any | Cloning the repo |

> **Optional:** [Docker](https://www.docker.com/) if you want to run the full stack via `docker-compose`.

---

## 1. Clone the Repository

```bash
git clone https://github.com/prathmesh-nitnaware/Prep_AI.git
cd Prep_AI
```

---

## 2. Get Your API Keys & Services

You need to set up external services before configuring environment variables.

### 🗄️ Database — Neon PostgreSQL (Free)
1. Go to [neon.tech](https://neon.tech) and create a free account.
2. Create a new project → copy the **Connection String** (looks like `postgresql://user:pass@host/db?sslmode=require`).

### 🤖 AI — Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Create API Key** → copy it.

### 🔐 Google OAuth Client ID (for Google Sign-In)
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth 2.0 Client ID**.
3. Application type: **Web application**.
4. Add authorized JavaScript origins:
   - `http://localhost:5173` (dev)
   - Your production frontend URL (if deploying)
5. Copy the **Client ID**.

### 📧 Gmail App Password (optional — for email verification)
1. Enable 2FA on your Google account.
2. Go to [Google Account → App Passwords](https://myaccount.google.com/apppasswords).
3. Create an app password for "Mail" → copy the 16-character password.

---

## 3. Backend Setup

```bash
cd backend
```

### 3a. Create a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3b. Install dependencies

```bash
pip install -r requirements.txt
```

### 3c. Configure environment variables

```bash
# Copy the example file
cp .env.example .env    # macOS/Linux
copy .env.example .env  # Windows
```

Open `backend/.env` and fill in your values:

```env
PORT=5000
SECRET_KEY=<generate a random 32+ character string>
ENVIRONMENT=development

# Paste your Neon connection string
DATABASE_URL=postgresql://<user>:<pass>@<host>/<db>?sslmode=require

# Paste your Gemini API key
GEMINI_API_KEY=<your_gemini_api_key>

# Email (optional — leave EMAIL_VERIFICATION_ENABLED=False to skip)
EMAIL_VERIFICATION_ENABLED=False
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=<your_gmail_app_password>

FRONTEND_URL=http://localhost:5173
```

> **Tip:** Generate a secret key with Python:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

### 3d. Run the backend

```bash
python main.py
```

Backend will be available at → **http://localhost:5000**

Verify it is running:
```
http://localhost:5000/api/health
```
Expected response: `{"status": "production-ready", "ai": "active"}`

---

## 4. Frontend Setup

Open a **new terminal** and:

```bash
cd frontend
```

### 4a. Install dependencies

```bash
npm install
```

### 4b. Configure environment variables

```bash
# Copy the example file
cp .env.example .env    # macOS/Linux
copy .env.example .env  # Windows
```

Open `frontend/.env` and fill in:

```env
# Point to your local backend
VITE_API_URL=http://localhost:5000

# Paste your Google OAuth Client ID
VITE_GOOGLE_CLIENT_ID=<your_google_oauth_client_id>
```

### 4c. Run the frontend

```bash
npm run dev
```

Frontend will be available at → **http://localhost:5173**

---

## 5. Verify Everything Works

With both servers running, open your browser to:

```
http://localhost:5173
```

Test these flows:
- [ ] Register a new account
- [ ] Log in (email/password)
- [ ] Log in with Google
- [ ] Start a mock interview

---

## 6. (Optional) Run with Docker Compose

If you prefer Docker over manual setup:

```bash
# From the repo root
cp backend/.env.example backend/.env
# Fill in backend/.env with your credentials (same as Step 3c)

docker compose up --build
```

This spins up:
- **3× Flask backend instances** (load balanced)
- **React frontend** (served via Nginx)
- **Nginx edge load balancer** on port 80

> Note: The Docker setup reads `backend/.env` — make sure it is filled before running.

---

## 7. Project Structure

```
Prep_AI/
├── backend/               # Flask API server
│   ├── app/               # Controllers, interview logic
│   ├── routes/            # API route definitions
│   ├── services/          # AI, email, auth services
│   ├── models/            # Database models
│   ├── utils/             # Helpers, middleware
│   ├── main.py            # Entry point
│   ├── config.py          # Config loaded from .env
│   └── requirements.txt   # Python dependencies
│
├── frontend/              # React + Vite SPA
│   ├── src/
│   │   ├── pages/         # Page components
│   │   ├── components/    # Reusable UI components
│   │   ├── context/       # Auth context / state
│   │   └── services/      # Axios API client
│   ├── package.json
│   └── vite.config.js
│
├── nginx/                 # Nginx config (Docker only)
├── docker-compose.yml     # Full stack Docker setup
├── README.md              # Project overview
└── SETUP.md               # You are here
```

---

## 8. Common Issues

### Backend fails to start — DATABASE_URL error
- Make sure `backend/.env` exists and `DATABASE_URL` is set correctly.
- Confirm your Neon DB is active (free tier pauses after inactivity — just visit the Neon dashboard to wake it).

### Google Sign-In not working
- Make sure `VITE_GOOGLE_CLIENT_ID` is set in `frontend/.env`.
- Check that `http://localhost:5173` is listed in **Authorized JavaScript Origins** in Google Cloud Console.

### CORS errors in browser
- Make sure both servers are running on the expected ports (`5000` for backend, `5173` for frontend).
- Confirm `ENVIRONMENT=development` in `backend/.env` (development mode allows localhost origins).

### pip install fails
- Make sure your virtual environment is activated (you should see `(.venv)` in your terminal prompt).

---

## 9. Deployment

| Component | Platform | Notes |
|---|---|---|
| Backend | [Render](https://render.com) | Set env vars in the Render dashboard |
| Frontend | [Vercel](https://vercel.com) | Set `VITE_*` vars in project settings |
| Database | [Neon](https://neon.tech) | Serverless PostgreSQL, free tier available |

Set the same environment variable values from your `.env` files directly in each platform's settings dashboard instead of uploading `.env` files.
