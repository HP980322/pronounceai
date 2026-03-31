# 🗣 PronounceAI — English Pronunciation & Grammar Coach

A browser-based English learning tool powered by **Google Gemini AI (free tier)**. Upload or record your voice and get instant feedback on pronunciation, grammar, and fluency — no account needed for users, no credit card needed for you.

---

## ✨ Features

- 🎵 **Upload audio** — drag & drop MP3, WAV, M4A, OGG, WEBM
- 🎙 **Live recording** — record in-browser with real-time waveform
- 🤖 **AI-powered feedback** (Gemini 2.5 Flash-Lite, free tier):
  - Fluency score (0–100)
  - Pronunciation issue detection
  - Grammar correction
  - Personalized improvement tips
- 🛡 **Rate limiting** — protects your free quota from abuse
- ✏️ **Text override** — paste text directly to skip audio

---

## 🆓 Free Tier Details

Uses **Gemini 2.5 Flash-Lite** — the most generous free Gemini model:

| Limit | Amount |
|-------|--------|
| Requests per day | 1,000 |
| Requests per minute | 15 |
| Cost | **$0** |
| Credit card required | No |

> ⚠️ The Gemini free tier **cannot be used to serve users in the EU/EEA/UK/Switzerland** per Google's terms.
>
> On the free tier, **your prompts may be used by Google to improve their models**.

---

## 🚀 Getting Started

### 1. Clone & install

```bash
git clone https://github.com/HP980322/pronounceai.git
cd pronounceai
npm install
```

### 2. Get a free Gemini API key

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **Create API Key** — no credit card needed

### 3. Configure

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=AIza...
```

### 4. Run

```bash
npm start        # production
npm run dev      # auto-reload (needs nodemon)
```

Open `http://localhost:3000`.

---

## 📁 Project Structure

```
pronounceai/
├── index.html       # Frontend UI
├── app.js           # Frontend JavaScript
├── server.js        # Express backend + Gemini proxy + rate limiter
├── package.json
├── .env.example     # Copy → .env, add your key
├── .gitignore
└── README.md
```

---

## 🛡 Rate Limiting

| Setting | Default | Env var |
|---------|---------|---------|
| Max requests per window | 5 | `RATE_LIMIT` |
| Window duration | 10 min | `RATE_WINDOW_MS` |
| Max transcript length | 2000 chars | `MAX_CHARS` |
| Allowed origin | `*` | `ALLOWED_ORIGIN` |

---

## 🚢 Deploying

### Railway (recommended)
1. Push to GitHub → connect at [railway.app](https://railway.app)
2. Set `GEMINI_API_KEY` in environment variables → deploy

### Render
Same steps at [render.com](https://render.com) — Web Service, Node environment.

### Heroku
```bash
heroku create
heroku config:set GEMINI_API_KEY=AIza...
git push heroku main
```

---

## 🌐 Browser Support

| Feature | Chrome | Edge | Firefox | Safari |
|---------|--------|------|---------|--------|
| Upload + record | ✅ | ✅ | ✅ | ✅ |
| Auto-transcription | ✅ | ✅ | ⚠️ | ⚠️ |

---

## 📄 License

MIT
