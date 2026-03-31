# PronounceAI - main.py
# FastAPI backend using:
#   - OpenAI Whisper (local, free) for speech-to-text
#   - language_tool_python (local, free) for grammar checking
# Zero API keys required.

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import whisper
import language_tool_python
import tempfile, os, time, re
from collections import defaultdict

app = FastAPI(title="PronounceAI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Load models once at startup
# --------------------------------------------------
print("Loading Whisper model (base.en)...")
WHISPER_MODEL = whisper.load_model("base.en")   # ~140 MB, English-only, fast
print("Loading LanguageTool...")
LT = language_tool_python.LanguageTool("en-US")  # local JVM-based checker
print("Ready!")

# --------------------------------------------------
# Simple in-memory rate limiter
# --------------------------------------------------
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "10"))          # requests per window
RATE_WINDOW = int(os.getenv("RATE_WINDOW_SECS", "600"))  # 10 minutes
ip_requests: dict = defaultdict(list)

def check_rate(ip: str):
    now = time.time()
    ip_requests[ip] = [t for t in ip_requests[ip] if now - t < RATE_WINDOW]
    if len(ip_requests[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few minutes.")
    ip_requests[ip].append(now)

# --------------------------------------------------
# Pronunciation scoring heuristics (no model needed)
# Based on phoneme-level patterns common in learners
# --------------------------------------------------
COMMON_ISSUES = [
    (r"\bth\b",         "'th' sounds (e.g. 'the', 'this') — try placing your tongue between your teeth"),
    (r"\bthe\b",        "'the' — often mispronounced as 'da' or 'ze'"),
    (r"[aeiou]{3,}",    "Long vowel clusters can be tricky — slow down on vowel-heavy words"),
    (r"\b\w*tion\b",    "'-tion' endings (e.g. 'nation') — should sound like 'shun'"),
    (r"\b\w*ing\b",     "'-ing' endings — make sure to voice the final 'g'"),
    (r"\b\w*ed\b",      "Past tense '-ed' endings have three sounds: /t/, /d/, or /ɪd/ — choose the right one"),
    (r"\b(w|wh)\w+",   "Words starting with 'w/wh' — lips should be rounded, not open"),
    (r"\bv\w+",         "Words starting with 'v' — upper teeth touch lower lip (don't confuse with 'b')"),
    (r"\br\w+",         "Words starting with 'r' — tongue should not touch the roof of your mouth"),
    (r"\bl\w+",         "Words starting with 'l' — tongue tip touches the ridge behind upper teeth"),
]

def detect_pronunciation_issues(text: str) -> list[str]:
    issues = []
    words = text.lower()
    for pattern, tip in COMMON_ISSUES:
        if re.search(pattern, words):
            issues.append(tip)
    return issues[:4]  # cap at 4 tips

# --------------------------------------------------
# Grammar analysis with LanguageTool
# --------------------------------------------------
def analyze_grammar(text: str):
    matches = LT.check(text)
    corrected = language_tool_python.utils.correct(text, matches)

    issues = []
    for m in matches[:6]:  # show up to 6 issues
        rule_desc = m.message
        context   = m.context.strip()
        issues.append(f"{rule_desc}  [context: ...{context}...]")

    return corrected, issues

# --------------------------------------------------
# Scoring
# --------------------------------------------------
def compute_score(text: str, grammar_issues: list, pron_issues: list) -> tuple[int, str]:
    words = text.split()
    word_count = max(len(words), 1)

    # Deduct points per grammar error (scaled by length)
    grammar_penalty = min(len(grammar_issues) * 8, 40)
    pron_penalty    = min(len(pron_issues)    * 5, 25)
    length_bonus    = min(word_count * 2, 15)  # reward longer speech

    raw = 100 - grammar_penalty - pron_penalty + length_bonus
    score = max(10, min(100, raw))

    if score >= 90:
        summary = f"Excellent English! Your speech is very natural with {word_count} words. Minor tweaks could make it perfect."
    elif score >= 75:
        summary = f"Good English overall! {word_count} words with only a few areas to polish. Keep practicing!"
    elif score >= 55:
        summary = f"Solid intermediate English. Your {word_count}-word message had some grammar or pronunciation patterns to work on."
    elif score >= 35:
        summary = f"Developing English skills shown in your {word_count}-word message. Focus on the grammar and pronunciation tips below."
    else:
        summary = f"Keep practicing! Your {word_count}-word message shows you are learning. Review the corrections and tips carefully."

    return score, summary

# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "transcription": "whisper-base.en", "grammar": "languagetool-local"}


@app.post("/api/analyze-audio")
async def analyze_audio(file: UploadFile = File(...), request_ip: str = Form(default="unknown")):
    """Accept an audio file, transcribe it with Whisper, then analyze."""
    check_rate(request_ip)

    # Save upload to temp file
    suffix = os.path.splitext(file.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # Transcribe
        result = WHISPER_MODEL.transcribe(tmp_path, language="en", fp16=False)
        transcript = result["text"].strip()
    finally:
        os.unlink(tmp_path)

    if not transcript:
        raise HTTPException(status_code=422, detail="Could not transcribe audio. Please speak clearly or paste text.")

    return _build_response(transcript)


@app.post("/api/analyze-text")
async def analyze_text(payload: dict):
    """Accept plain text and analyze grammar + pronunciation."""
    transcript = (payload.get("text") or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="text is required.")
    if len(transcript) > 3000:
        raise HTTPException(status_code=400, detail="Text too long (max 3000 characters).")
    return _build_response(transcript)


def _build_response(transcript: str) -> dict:
    corrected, grammar_issues = analyze_grammar(transcript)
    pron_issues               = detect_pronunciation_issues(transcript)
    score, summary            = compute_score(transcript, grammar_issues, pron_issues)

    tips = [
        "Read English aloud every day for 10 minutes — BBC News or TED Talks work great.",
        "Record yourself and compare to native speakers — you will hear differences you miss live.",
        "Practice minimal pairs (e.g. 'ship/sheep', 'bit/beat') to sharpen vowel sounds.",
        "Slow down! Clarity beats speed — native listeners appreciate it.",
    ]

    return {
        "transcript":           transcript,
        "score":                score,
        "summary":              summary,
        "pronunciation_issues": pron_issues,
        "corrected_sentence":   corrected,
        "grammar_issues":       grammar_issues,
        "tips":                 tips,
    }


# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
