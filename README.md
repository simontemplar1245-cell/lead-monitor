# Lead Monitor - Advance AI Services

Automated lead detection system that monitors 30+ online communities for people who need AI chatbots and AI phone receptionists. Finds leads, classifies them with AI, and alerts you instantly via Telegram.

## How It Works

```
Every 30 minutes (via GitHub Actions):

  Reddit (30+ subreddits) ─────┐
  Industry forums ─────────────┤
  Hacker News ─────────────────┼─→ Keyword Filter ─→ Claude Haiku ─→ HOT? ─→ Telegram Alert
  Bluesky ─────────────────────┘   (free, fast)      (classifies)         (instant)
                                                                    ─→ WARM? ─→ Daily Digest
                                                                    ─→ COLD? ─→ Ignored
```

## Quick Start

### 1. Create your API credentials (15 mins, all free)

| Service | Where | What you get |
|---------|-------|-------------|
| Reddit API | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → "script" type | `client_id` + `client_secret` |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/settings/keys) | `api_key` |
| Telegram | Open Telegram → @BotFather → /newbot | `bot_token` + `chat_id` |

**Getting your Telegram chat_id:** After creating your bot, send it any message, then visit:
```
https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
```
Look for `"chat":{"id":123456789}` — that number is your chat_id.

### 2. Add secrets to GitHub

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these secrets:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USERNAME`
- `REDDIT_PASSWORD`
- `ANTHROPIC_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 3. Enable GitHub Actions

Go to your repo → **Actions** tab → Click **"I understand my workflows, go ahead and enable them"**

The monitor will start running automatically every 30 minutes.

### 4. Deploy the dashboard (optional)

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Connect your GitHub account
3. Select this repo
4. Set main file path to: `dashboard/app.py`
5. Add secrets in Streamlit's settings (same as GitHub secrets)

## Running Locally

```bash
# Clone the repo
git clone https://github.com/simontemplar1245-cell/lead-monitor.git
cd lead-monitor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (needed for some forums)
playwright install chromium

# Copy environment file and fill in your keys
cp .env.example .env
# Edit .env with your actual API keys

# Run a test scan (no notifications)
python main.py --test

# Run a full scan
python main.py

# Run specific platforms
python main.py --reddit
python main.py --forums
python main.py --hn
python main.py --bluesky

# Send daily digest
python main.py --digest

# Start the dashboard
streamlit run dashboard/app.py
```

## What It Monitors

### Reddit (30+ subreddits)
**Trades/Contractors:** r/sweatystartup, r/electricians, r/HVAC, r/plumbing, r/pressurewashing, r/lawncare, r/Roofing, r/CleaningService

**Dental:** r/Dentistry

**Legal:** r/Lawyertalk, r/LawFirm

**Real Estate:** r/realtors

**Insurance:** r/InsuranceAgent

**Salon/Beauty:** r/hairstylist

**Restaurants:** r/restaurantowners

**E-commerce:** r/ecommerce, r/shopify

**General Business:** r/smallbusiness, r/Entrepreneur, r/EntrepreneurRideAlong

### Industry Forums
- Dentaltown.com (250k+ dental professionals)
- ContractorTalk.com (contractor business forum)
- HVACTalk.com (HVAC professionals)
- LawnSite.com (lawn/landscaping business, 7M+ posts)
- Insurance-Forums.com (insurance agents)

### Other Platforms
- Hacker News (via free Algolia API)
- Bluesky (via public AT Protocol API)

## Pain-Point Keywords (Not Solution Keywords)

We search for what buyers **actually say**, not what competitors search for:

| Instead of searching for... | We search for... |
|---|---|
| "AI chatbot" | "missed calls", "receptionist quit", "can't answer the phone" |
| "virtual receptionist" | "front desk left", "covering phones myself", "voicemail killing business" |
| "customer service automation" | "too many support tickets", "can't keep up with messages" |

## Monthly Cost

| Component | Cost |
|-----------|------|
| GitHub Actions | Free |
| Reddit API | Free |
| Hacker News API | Free |
| Bluesky API | Free |
| Claude Haiku classification | ~$1-2 |
| Telegram alerts | Free |
| Streamlit dashboard | Free |
| **Total** | **~$1-2/month** |

## Project Structure

```
lead-monitor/
├── .github/workflows/
│   └── monitor.yml          ← Runs every 30 min on GitHub
├── scrapers/
│   ├── reddit_scraper.py     ← Reddit via PRAW
│   ├── forum_scraper.py      ← Forums via BeautifulSoup/Playwright
│   ├── hackernews_scraper.py ← HN via Algolia API
│   └── bluesky_scraper.py    ← Bluesky via AT Protocol
├── core/
│   ├── classifier.py         ← Claude Haiku lead classification
│   ├── database.py           ← SQLite database layer
│   └── notifier.py           ← Telegram alerts
├── dashboard/
│   └── app.py                ← Streamlit web dashboard
├── config.py                 ← All settings, keywords, subreddits
├── main.py                   ← Entry point
├── requirements.txt
├── .env.example              ← Template for API keys
└── .gitignore
```
