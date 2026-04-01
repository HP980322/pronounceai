# PronounceAI - main.py
# Slim FastAPI backend:
#   - ElevenLabs proxy (voice clone + TTS) — key stays on server
#   - Grammar + analysis done client-side via LanguageTool public API
#   - Transcription done client-side via browser Speech API

from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx, io, os, time
from collections import defaultdict

app = FastAPI(title="PronounceAI", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EL_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
EL_BASE    = "https://api.elevenlabs.io/v1"

# Simple rate limiter
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

@app.post("/api/clone-voice")
async def clone_voice(request: Request, file: UploadFile = File(...)):
    check_rate(get_ip(request))
    if not EL_API_KEY:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not set on server.")
    audio = await file.read()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{EL_BASE}/voices/add",
            headers={"xi-api-key": EL_API_KEY},
            files={"files": ("voice.webm", io.BytesIO(audio), "audio/webm")},
            data={"name": f"PronounceAI-{int(time.time())}", "description": "PronounceAI voice clone"},
        )
    if not resp.is_success:
        detail = resp.json().get("detail", {}).get("message", f"ElevenLabs error {resp.status_code}")
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return {"voice_id": resp.json()["voice_id"]}

@app.post("/api/speak")
async def speak(request: Request, payload: dict):
    check_rate(get_ip(request))
    if not EL_API_KEY:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not set on server.")
    voice_id = payload.get("voice_id", "").strip()
    text     = (payload.get("text") or "").strip()
    if not voice_id or not text:
        raise HTTPException(status_code=400, detail="voice_id and text are required.")
    if len(text) > 3000:
        raise HTTPException(status_code=400, detail="Text too long.")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{EL_BASE}/text-to-speech/{voice_id}",
            headers={"xi-api-key": EL_API_KEY, "Accept": "audio/mpeg", "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_turbo_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.85, "style": 0.2, "use_speaker_boost": True}},
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=f"ElevenLabs TTS error {resp.status_code}")
    return StreamingResponse(io.BytesIO(resp.content), media_type="audio/mpeg")

@app.delete("/api/delete-voice/{voice_id}")
async def delete_voice(voice_id: str, request: Request):
    if not EL_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured.")
    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{EL_BASE}/voices/{voice_id}", headers={"xi-api-key": EL_API_KEY})
    return {"deleted": voice_id}

# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
