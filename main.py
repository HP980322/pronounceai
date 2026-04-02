# PronounceAI - main.py
# Uses Microsoft Edge TTS (free, no API key, high quality)
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io, os, time
from collections import defaultdict
import edge_tts

app = FastAPI(title="PronounceAI", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# High quality Edge TTS voices
VOICES = [
    {"id": "en-US-JennyNeural",      "name": "Jenny",    "description": "Friendly, female, American"},
    {"id": "en-US-AriaNeural",       "name": "Aria",     "description": "Natural, female, American"},
    {"id": "en-US-GuyNeural",        "name": "Guy",      "description": "Clear, male, American"},
    {"id": "en-US-EricNeural",       "name": "Eric",     "description": "Calm, male, American"},
    {"id": "en-US-SaraNeural",       "name": "Sara",     "description": "Warm, female, American"},
    {"id": "en-US-ChristopherNeural","name": "Christopher","description": "Deep, male, American"},
    {"id": "en-US-AnaNeural",        "name": "Ana",      "description": "Young, female, American"},
    {"id": "en-US-BrandonNeural",    "name": "Brandon",  "description": "Strong, male, American"},
    {"id": "en-GB-SoniaNeural",      "name": "Sonia",    "description": "Warm, female, British"},
    {"id": "en-GB-RyanNeural",       "name": "Ryan",     "description": "Natural, male, British"},
    {"id": "en-GB-LibbyNeural",      "name": "Libby",    "description": "Friendly, female, British"},
    {"id": "en-AU-NatashaNeural",    "name": "Natasha",  "description": "Clear, female, Australian"},
    {"id": "en-AU-WilliamNeural",    "name": "William",  "description": "Warm, male, Australian"},
    {"id": "en-IN-NeerjaNeural",     "name": "Neerja",   "description": "Bright, female, Indian"},
    {"id": "en-CA-ClaraNeural",      "name": "Clara",    "description": "Pleasant, female, Canadian"},
]

RATE_LIMIT  = int(os.getenv("RATE_LIMIT", "20"))
RATE_WINDOW = int(os.getenv("RATE_WINDOW_SECS", "600"))
ip_requests: dict = defaultdict(list)

def get_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")

def check_rate(ip: str):
    now = time.time()
    ip_requests[ip] = [t for t in ip_requests[ip] if now - t < RATE_WINDOW]
    if len(ip_requests[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests.")
    ip_requests[ip].append(now)

@app.get("/api/health")
def health():
    return {"status": "ok", "tts": "Microsoft Edge TTS (free)"}

@app.get("/api/voices")
def get_voices():
    return {"voices": VOICES}

@app.post("/api/speak")
async def speak(request: Request, payload: dict):
    check_rate(get_ip(request))
    voice_id = payload.get("voice_id", "en-US-JennyNeural").strip()
    text     = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    if len(text) > 3000:
        raise HTTPException(status_code=400, detail="Text too long.")
    try:
        communicate = edge_tts.Communicate(text, voice_id)
        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])
        audio_buffer.seek(0)
        return StreamingResponse(audio_buffer, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")

# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
