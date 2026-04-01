# PronounceAI - main.py
# FastAPI backend:
#   - Whisper (local) for speech-to-text
#   - LanguageTool (local) for grammar
#   - ElevenLabs (cloud) for voice cloning & TTS — key stays on server

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import whisper
import language_tool_python
import httpx, tempfile, os, time, re, io
from collections import defaultdict

app = FastAPI(title="PronounceAI", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Load local models once at startup
# --------------------------------------------------
print("Loading Whisper model (base.en)...")
WHISPER_MODEL = whisper.load_model("base.en")
print("Loading LanguageTool...")
LT = language_tool_python.LanguageTool("en-US")
print("Ready!")

EL_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
EL_BASE    = "https://api.elevenlabs.io/v1"

# --------------------------------------------------
# Rate limiter
# --------------------------------------------------
RATE_LIMIT  = int(os.getenv("RATE_LIMIT", "10"))
RATE_WINDOW = int(os.getenv("RATE_WINDOW_SECS", "600"))
ip_requests: dict = defaultdict(list)

def get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host

def check_rate(ip: str):
    now = time.time()
    ip_requests[ip] = [t for t in ip_requests[ip] if now - t < RATE_WINDOW]
    if len(ip_requests[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few minutes.")
    ip_requests[ip].append(now)

# --------------------------------------------------
# Pronunciation heuristics
# --------------------------------------------------
COMMON_ISSUES = [
    (r"\bth[eaio]",    "'th' sounds — place your tongue lightly between your teeth"),
    (r"tion\b",        "'-tion' endings — pronounce as 'shun' (e.g. na-SHUN)"),
    (r"\w+ing\b",      "'-ing' endings — voice the final 'g' clearly"),
    (r"\w+ed\b",       "Past '-ed' endings have 3 sounds: /t/, /d/, or /ɪd/ — choose carefully"),
    (r"\bv\w+",        "Words with 'v' — upper teeth touch lower lip (not like 'b')"),
    (r"\br\w+",        "Words with 'r' — tongue should NOT touch the roof of your mouth"),
    (r"\bl\w+",        "Words with 'l' — tongue tip touches just behind upper teeth"),
    (r"\bw[aeio]",     "Words with 'w' — round your lips before speaking"),
]

def detect_pron(text: str) -> list[str]:
    return [tip for pat, tip in COMMON_ISSUES if re.search(pat, text.lower())][:4]

# --------------------------------------------------
# Grammar
# --------------------------------------------------
def analyze_grammar(text: str):
    matches  = LT.check(text)
    corrected = language_tool_python.utils.correct(text, matches)
    issues   = [f"{m.message}  [...{m.context.strip()}...]" for m in matches[:6]]
    return corrected, issues

# --------------------------------------------------
# Scoring
# --------------------------------------------------
def compute_score(text: str, gram: list, pron: list):
    wc   = max(len(text.split()), 1)
    raw  = 100 - min(len(gram)*8, 40) - min(len(pron)*5, 25) + min(wc*2, 15)
    sc   = max(10, min(100, raw))
    msgs = [
        (90, f"Excellent! Your {wc}-word message is very natural."),
        (75, f"Good English! {wc} words with a few areas to polish."),
        (55, f"Solid intermediate English. {wc} words — work on the corrections below."),
        (35, f"Developing skills in your {wc}-word message."),
    ]
    summary = next((m for s, m in msgs if sc >= s), f"Keep practicing! Review all corrections carefully.")
    return sc, summary

# --------------------------------------------------
# Build analysis response
# --------------------------------------------------
def _build_response(transcript: str) -> dict:
    corrected, grammar_issues = analyze_grammar(transcript)
    pron_issues               = detect_pron(transcript)
    score, summary            = compute_score(transcript, grammar_issues, pron_issues)
    return {
        "transcript":           transcript,
        "score":                score,
        "summary":              summary,
        "pronunciation_issues": pron_issues,
        "corrected_sentence":   corrected,
        "grammar_issues":       grammar_issues,
        "tips": [
            "Listen to the corrected version and repeat it out loud immediately.",
            "Read English aloud 10 min/day — BBC News or TED Talks work great.",
            "Practice minimal pairs: ship/sheep, bit/beat, cat/cut.",
            "Slow down — clarity always beats speed.",
        ],
    }

# --------------------------------------------------
# Analysis routes
# --------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "elevenlabs": bool(EL_API_KEY)}

@app.post("/api/analyze-audio")
async def analyze_audio(request: Request, file: UploadFile = File(...)):
    check_rate(get_ip(request))
    suffix = os.path.splitext(file.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result     = WHISPER_MODEL.transcribe(tmp_path, language="en", fp16=False)
        transcript = result["text"].strip()
    finally:
        os.unlink(tmp_path)
    if not transcript:
        raise HTTPException(status_code=422, detail="Could not transcribe. Please speak clearly or use the Text tab.")
    return _build_response(transcript)

@app.post("/api/analyze-text")
async def analyze_text(request: Request, payload: dict):
    check_rate(get_ip(request))
    transcript = (payload.get("text") or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="text is required.")
    if len(transcript) > 3000:
        raise HTTPException(status_code=400, detail="Text too long (max 3000 characters).")
    return _build_response(transcript)

# --------------------------------------------------
# ElevenLabs proxy routes (key stays on server)
# --------------------------------------------------

@app.post("/api/clone-voice")
async def clone_voice(request: Request, file: UploadFile = File(...)):
    """Upload a voice sample, create an ElevenLabs instant voice clone."""
    check_rate(get_ip(request))
    if not EL_API_KEY:
        raise HTTPException(status_code=503, detail="Voice cloning not configured on this server. Set ELEVENLABS_API_KEY in .env")

    audio_bytes = await file.read()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{EL_BASE}/voices/add",
            headers={"xi-api-key": EL_API_KEY},
            files={"files": ("voice-sample.webm", io.BytesIO(audio_bytes), "audio/webm")},
            data={"name": f"PronounceAI-{int(time.time())}", "description": "PronounceAI voice clone"},
        )
    if not resp.is_success:
        detail = resp.json().get("detail", {}).get("message", f"ElevenLabs error {resp.status_code}")
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return {"voice_id": resp.json()["voice_id"]}

@app.post("/api/speak")
async def speak(request: Request, payload: dict):
    """Convert text to speech using the cloned voice. Streams MP3 audio."""
    check_rate(get_ip(request))
    if not EL_API_KEY:
        raise HTTPException(status_code=503, detail="Voice cloning not configured on this server.")

    voice_id = payload.get("voice_id", "").strip()
    text     = (payload.get("text") or "").strip()
    if not voice_id or not text:
        raise HTTPException(status_code=400, detail="voice_id and text are required.")
    if len(text) > 3000:
        raise HTTPException(status_code=400, detail="Text too long (max 3000 characters).")

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
    """Delete a cloned voice from ElevenLabs."""
    if not EL_API_KEY:
        raise HTTPException(status_code=503, detail="Not configured.")
    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{EL_BASE}/voices/{voice_id}", headers={"xi-api-key": EL_API_KEY})
    return {"deleted": voice_id}

# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
