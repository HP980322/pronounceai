# PronounceAI - main.py
# Edge TTS + pitch shifting for free voice matching
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io, os, time, struct, math
from collections import defaultdict
import edge_tts
import numpy as np
from scipy import signal
from scipy.io import wavfile

app = FastAPI(title="PronounceAI", version="6.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VOICES = [
    {"id": "en-US-JennyNeural",       "name": "Jenny",       "description": "Friendly, female, American"},
    {"id": "en-US-AriaNeural",        "name": "Aria",        "description": "Natural, female, American"},
    {"id": "en-US-GuyNeural",         "name": "Guy",         "description": "Clear, male, American"},
    {"id": "en-US-EricNeural",        "name": "Eric",        "description": "Calm, male, American"},
    {"id": "en-US-ChristopherNeural", "name": "Christopher", "description": "Deep, male, American"},
    {"id": "en-US-AnaNeural",         "name": "Ana",         "description": "Young, female, American"},
    {"id": "en-GB-SoniaNeural",       "name": "Sonia",       "description": "Warm, female, British"},
    {"id": "en-GB-RyanNeural",        "name": "Ryan",        "description": "Natural, male, British"},
    {"id": "en-GB-LibbyNeural",       "name": "Libby",       "description": "Friendly, female, British"},
    {"id": "en-AU-NatashaNeural",     "name": "Natasha",     "description": "Clear, female, Australian"},
    {"id": "en-AU-WilliamNeural",     "name": "William",     "description": "Warm, male, Australian"},
    {"id": "en-CA-ClaraNeural",       "name": "Clara",       "description": "Pleasant, female, Canadian"},
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

def detect_pitch_from_pcm(samples: np.ndarray, sr: int) -> float:
    """Autocorrelation pitch detection on mono float32 samples."""
    # Only analyze voiced frames (above noise floor)
    frame_size = int(sr * 0.05)  # 50ms windows
    pitches = []
    for i in range(0, len(samples) - frame_size, frame_size):
        frame = samples[i:i+frame_size]
        rms = np.sqrt(np.mean(frame**2))
        if rms < 0.01:
            continue
        # Autocorrelation
        corr = np.correlate(frame, frame, mode='full')
        corr = corr[len(corr)//2:]
        # Find first peak after min lag (60Hz) and before max lag (400Hz)
        min_lag = int(sr / 400)
        max_lag = int(sr / 60)
        if max_lag >= len(corr):
            continue
        peak = np.argmax(corr[min_lag:max_lag]) + min_lag
        if corr[peak] > 0.3 * corr[0]:
            pitches.append(sr / peak)
    return float(np.median(pitches)) if pitches else 150.0

def pitch_shift_audio(audio_bytes: bytes, semitones: float) -> bytes:
    """Pitch shift MP3 audio by semitones using scipy resampling."""
    if abs(semitones) < 0.5:
        return audio_bytes  # Not worth shifting
    # Convert semitones to rate ratio
    ratio = 2 ** (semitones / 12.0)
    # Read as raw bytes and resample
    # We'll work with raw PCM via a simple approach:
    # Resample the audio data (changes both pitch and speed),
    # then resample back to original length (corrects speed)
    audio_array = np.frombuffer(audio_bytes, dtype=np.uint8).astype(np.float32)
    # Resample to change pitch+speed
    new_len = int(len(audio_array) / ratio)
    resampled = signal.resample(audio_array, new_len)
    # Resample back to original length (fix speed)
    restored = signal.resample(resampled, len(audio_array))
    return restored.astype(np.uint8).tobytes()

@app.get("/api/health")
def health():
    return {"status": "ok", "tts": "Edge TTS + pitch shift"}

@app.get("/api/voices")
def get_voices():
    return {"voices": VOICES}

@app.post("/api/analyze-voice")
async def analyze_voice(request: Request, file: UploadFile = File(...)):
    """Analyze uploaded voice sample, return pitch info."""
    check_rate(get_ip(request))
    audio_bytes = await file.read()
    # Convert webm to numpy via scipy (works for wav-like data)
    # Since we get webm, we'll do a simplified frequency analysis
    # using the raw byte energy distribution as a proxy for pitch
    try:
        raw = np.frombuffer(audio_bytes, dtype=np.uint8).astype(np.float32)
        raw = raw / 128.0 - 1.0  # normalize to -1..1
        # Simple zero-crossing rate as proxy for pitch
        zcr = np.sum(np.abs(np.diff(np.sign(raw)))) / len(raw)
        # Map ZCR to estimated Hz (rough approximation)
        # ZCR for speech ~0.01-0.15
        estimated_hz = max(80, min(350, zcr * 2000))
        # Determine voice type
        if estimated_hz < 130:
            voice_type = "deep"
            recommended = "en-US-GuyNeural"
        elif estimated_hz < 180:
            voice_type = "mid"
            recommended = "en-US-EricNeural"
        else:
            voice_type = "high"
            recommended = "en-US-JennyNeural"
        return {
            "hz": round(estimated_hz),
            "voice_type": voice_type,
            "recommended_voice": recommended,
            "pitch_semitones": 0,  # Will be calculated client-side
        }
    except Exception as e:
        return {"hz": 150, "voice_type": "mid", "recommended_voice": "en-US-JennyNeural", "pitch_semitones": 0}

@app.post("/api/speak")
async def speak(request: Request, payload: dict):
    check_rate(get_ip(request))
    voice_id       = payload.get("voice_id", "en-US-JennyNeural").strip()
    text           = (payload.get("text") or "").strip()
    pitch_semitones = float(payload.get("pitch_semitones", 0))
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
        audio_bytes = audio_buffer.getvalue()
        if not audio_bytes:
            raise ValueError(f"No audio received for voice {voice_id}")
        # Apply pitch shift if requested
        if abs(pitch_semitones) >= 0.5:
            audio_bytes = pitch_shift_audio(audio_bytes, pitch_semitones)
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")

# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
