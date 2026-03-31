# Pronounce**AI** — English Pronunciation & Grammar Coach

> **100% local. Zero API keys. Zero cost. No internet required after install.**

Like a background remover that runs locally — PronounceAI uses:
- **[OpenAI Whisper](https://github.com/openai/whisper)** — local speech-to-text (~140 MB model, runs on CPU)
- **[LanguageTool](https://languagetool.org)** — local grammar checker (open-source, JVM-based)
- **[FastAPI](https://fastapi.tiangolo.com)** — lightweight Python web framework

---

## Features

- Upload audio (MP3, WAV, M4A, OGG, WEBM, FLAC) or record live
- Auto-transcription with Whisper running locally
- Grammar correction with LanguageTool
- Pronunciation pattern tips
- Fluency score and summary
- Text-only mode (paste text to skip audio)
- Your voice **never leaves your machine**

---

## Requirements

- Python 3.9+
- Java 8+ (required by LanguageTool — check with `java -version`)
- ~500 MB disk space (Whisper model + LanguageTool data, downloaded on first run)
- ffmpeg (required by Whisper for audio decoding)

### Install ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

---

## Getting Started

### 1. Clone

```bash
git clone https://github.com/HP980322/pronounceai.git
cd pronounceai
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

On first run, Whisper will automatically download the `base.en` model (~140 MB).
LanguageTool will download its grammar data (~200 MB) the first time it runs.

### 3. Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

First startup takes 30-60 seconds while models load. Subsequent requests are fast.

---

## Project Structure

```
pronounceai/
├── main.py              # FastAPI app (Whisper + LanguageTool)
├── requirements.txt
├── static/
│   ├── index.html       # Frontend UI
│   └── app.js           # Frontend JavaScript
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/analyze-audio` | Upload audio file → transcribe + analyze |
| `POST` | `/api/analyze-text` | Send text → analyze grammar |

---

## Environment Variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT` | `10` | Max requests per window per IP |
| `RATE_WINDOW_SECS` | `600` | Rate window in seconds |

---

## Models Used

| Model | Size | Purpose | Runs on |
|-------|------|---------|----------|
| `whisper-base.en` | ~140 MB | Speech-to-text | CPU (or GPU if available) |
| `LanguageTool en-US` | ~200 MB | Grammar checking | JVM (local) |

To use a more accurate (but slower) Whisper model, change `"base.en"` to `"small.en"` or `"medium.en"` in `main.py`.

---

## Privacy

- Audio is processed entirely on your machine
- No data is sent to any external server
- No API keys, no accounts, no tracking

---

## License

MIT
