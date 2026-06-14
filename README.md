# AI Resume & Job Application Bot 🤖📄

A **Telegram-native AI career assistant** that lets job seekers instantly optimize
their resume, generate a tailored cover letter, and score ATS (Applicant Tracking
System) compatibility — all without leaving Telegram.

Built to the product spec in `AI_Resume_Bot_PRD.docx` (India-focused, freemium +
pay-per-use + subscription).

---

## ✨ Features (MVP / V1.0)

| Feature | Status | PRD ref |
|---|---|---|
| Resume upload (PDF / DOCX) | ✅ | §5.1 |
| Job description paste | ✅ | §5.1 |
| AI resume rewrite (keyword-matched to the JD) | ✅ | §5.1 |
| ATS score — before vs. after (0–100) | ✅ | §5.1, §7.2 |
| Cover letter generation | ✅ | §5.1 |
| PDF download of output | ✅ | §5.1 |
| Usage limits (3 free rewrites → paywall) | ✅ | §5.1 |
| Payments: Razorpay links + Telegram Stars | ✅ | §5.1, §8.2 |
| Auto-quota update on payment webhook | ✅ | §8.2 |
| File auto-deletion + hashed user IDs | ✅ | §7.3 |

The core user journey (PRD §6.1): **/start → upload resume → paste JD →
[Rewrite] / [Cover Letter] / [Both] → ATS score + downloadable PDF → paywall when
the free quota runs out.**

---

## 🏗️ Architecture

```
bot/
├── main.py                 # entry point: wires handlers, starts webhook + bot
├── config.py               # env-driven settings (pydantic-settings)
├── database.py             # SQLAlchemy async models (User, Payment) + helpers
├── handlers/
│   ├── commands.py         # /start /help /status /reset /privacy
│   ├── flow.py             # upload → JD → action → ATS + PDF (the core flow)
│   ├── payments.py         # paywall, Razorpay links, Telegram Stars
│   └── keyboards.py        # inline keyboards + callback-data constants
├── services/
│   ├── parsing.py          # PDF/DOCX → text (pdfplumber, python-docx, pypdf)
│   ├── ats.py              # TF-IDF + keyword overlap ATS scoring (§7.2)
│   ├── ai.py               # Claude API: rewrite + cover letter
│   ├── pdf.py              # text → ATS-friendly PDF (reportlab)
│   ├── quota.py            # free / paid-credit / pro precedence
│   ├── plans.py            # pricing tiers (§8.1)
│   ├── razorpay_client.py  # Razorpay payment-link creation
│   └── files.py            # temp-file handling + retention cleanup (§7.3)
└── webhook/
    └── server.py           # aiohttp server for Razorpay confirmations
```

**Stack** (PRD §7.1): `python-telegram-bot` v21 · Anthropic Claude API ·
`pdfplumber`/`python-docx` · scikit-learn (TF-IDF cosine) · `reportlab` ·
SQLAlchemy (SQLite locally, Postgres in prod) · Razorpay + Telegram Stars.

---

## 🚀 Getting started

### 1. Prerequisites
- Python 3.11+
- A Telegram bot token from [@BotFather](https://core.telegram.org/bots#botfather)
- An [Anthropic API key](https://console.anthropic.com/)
- (Optional) Razorpay keys for ₹ payments

### 2. Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure
```bash
cp .env.example .env
# edit .env: set TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY (and Razorpay keys if used)
```

### 4. Run
```bash
python -m bot.main
```
The bot starts in long-polling mode. If Razorpay keys are configured, the webhook
server also starts on `WEBHOOK_PORT` (default 8080).

### 5. Test
```bash
pip install -r requirements-dev.txt
pytest
```

---

## 💳 Payments

**Telegram Stars** work out of the box (`ENABLE_TELEGRAM_STARS=true`) — no provider
token needed; quota is credited on the in-chat `successful_payment`.

**Razorpay** (best for the India launch):
1. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
2. Expose `PUBLIC_BASE_URL` (e.g. via your host or a tunnel).
3. In the Razorpay dashboard, add a webhook pointing at
   `<PUBLIC_BASE_URL>/razorpay/webhook` for the `payment_link.paid` event, using
   the same secret.
4. On payment, the webhook verifies the HMAC signature, credits the user, and
   messages them in Telegram automatically.

Pricing tiers (PRD §8.1): Free (3 lifetime) · Rewrite Pack 5 (₹99) · Rewrite Pack
20 (₹299) · Monthly Pro (₹499, unlimited 30 days).

---

## 🔒 Privacy (PRD §7.3)
- Telegram user IDs are **hashed** (salted SHA-256) before storage.
- Uploaded files are deleted right after parsing, and a periodic job purges
  anything older than `FILE_RETENTION_HOURS` (default 24h).
- No PII is written to logs.

---

## ⚙️ Configuration reference
See [`.env.example`](./.env.example) for every supported variable. Notable ones:

| Var | Default | Notes |
|---|---|---|
| `ANTHROPIC_MODEL` | `claude-opus-4-8` | `claude-sonnet-4-6` is the cheaper alternative for scale (PRD open question §11) |
| `ANTHROPIC_EFFORT` | `medium` | `low`/`medium`/`high`/`max` — trades cost/latency for depth |
| `FREE_REWRITES` | `3` | Lifetime free allowance before the paywall |
| `DATABASE_URL` | SQLite file | Use a `postgresql+asyncpg://…` URL in production |
| `FILE_RETENTION_HOURS` | `24` | Auto-delete window for uploaded files |

---

## 🗺️ Roadmap (PRD §5.2, not yet built)
Multi-language (Hindi/Tamil/Telugu) · LinkedIn optimization · interview prep Q&A ·
bulk CSV rewrites for placement trainers · role-specific templates · OCR fallback
for scanned PDFs.

---

## 📦 Deploy
A `Dockerfile` is included:
```bash
docker build -t profolio-bot .
docker run --env-file .env -p 8080:8080 profolio-bot
```
Suitable for Railway / Render / an AWS EC2 `t3.small` (PRD §7.1).
