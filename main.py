# PronounceAI - main.py
# FastAPI backend:
#   - ElevenLabs TTS proxy using free pre-made voices
#   - No voice cloning required (works on free tier)

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx, io, os, time
from collections import defaultdict

app = FastAPI(title="PronounceAI", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EL_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
EL_BASE    = "https://api.elevenlabs.io/v1"

# Free ElevenLabs voices that work on the free tier
FREE_VOICES = [
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel",  "description": "Calm, female, American"},
    {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi",    "description": "Strong, female, American"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella",   "description": "Soft, female, American"},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni",  "description": "Warm, male, American"},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli",    "description": "Emotional, female, American"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh",    "description": "Deep, male, American"},
    {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold",  "description": "Crisp, male, American"},
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam",    "description": "Deep, male, American"},
    {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam",     "description": "Raspy, male, American"},
    {"id": "pMsXgVXv3BLzUgSXRplE", "name": "Serena",  "description": "Pleasant, female, American"},
    {"id": "g5CIjZEefAph4nQFvHAz", "name": "Ethan",   "description": "Soft, male, American"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel",  "description": "Deep, male, British"},
    {"id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte","description": "Seductive, female, Swedish"},
    {"id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice",   "description": "Confident, female, British"},
    {"id": "iP95p4xoKVk53GoZ742B", "name": "Chris",   "description": "Casual, male, American"},
]

# Rate limiter
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
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few minutes.")
    ip_requests[ip].append(now)

@app.get("/api/health")
def health():
    return {"status": "ok", "elevenlabs": bool(EL_API_KEY)}

@app.get("/api/voices")
def get_voices():
    """Return list of available free voices."""
    return {"voices": FREE_VOICES}

@app.post("/api/speak")
async def speak(request: Request, payload: dict):
    """Convert text to speech using a free ElevenLabs voice."""
    check_rate(get_ip(request))
    if not EL_API_KEY:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not set on server.")
    voice_id = payload.get("voice_id", "21m00Tcm4TlvDq8ikWAM")  # default: Rachel
    text     = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    if len(text) > 3000:
        raise HTTPException(status_code=400, detail="Text too long.")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{EL_BASE}/text-to-speech/{voice_id}",
            headers={"xi-api-key": EL_API_KEY, "Accept": "audio/mpeg", "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_turbo_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=f"ElevenLabs error {resp.status_code}")
    return StreamingResponse(io.BytesIO(resp.content), media_type="audio/mpeg")

# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
