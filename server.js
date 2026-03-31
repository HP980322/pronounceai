// PronounceAI - server.js
// Uses Gemini 2.5 Flash-Lite (free tier): 1,000 req/day, 15 RPM, no credit card

require('dotenv').config();
const express = require('express');
const cors    = require('cors');
const fetch   = (...a) => import('node-fetch').then(({ default: f }) => f(...a));

const app  = express();
const PORT = process.env.PORT || 3000;

const RATE_LIMIT     = parseInt(process.env.RATE_LIMIT     || '5');
const RATE_WINDOW_MS = parseInt(process.env.RATE_WINDOW_MS || String(10 * 60 * 1000));
const MAX_CHARS      = parseInt(process.env.MAX_CHARS      || '2000');

const ipMap = new Map();

function rateLimiter(req, res, next) {
  const ip  = req.headers['x-forwarded-for']?.split(',')[0].trim() || req.socket.remoteAddress;
  const now = Date.now();
  let entry = ipMap.get(ip);
  if (!entry || now > entry.resetAt) { entry = { count: 0, resetAt: now + RATE_WINDOW_MS }; ipMap.set(ip, entry); }
  entry.count++;
  if (entry.count > RATE_LIMIT) {
    const retryAfter = Math.ceil((entry.resetAt - now) / 1000);
    res.setHeader('Retry-After', retryAfter);
    return res.status(429).json({ error: `Too many requests. Please wait ${Math.ceil(retryAfter / 60)} minute(s) and try again.` });
  }
  if (ipMap.size > 1000) { for (const [k, v] of ipMap) if (now > v.resetAt) ipMap.delete(k); }
  next();
}

app.use(cors({ origin: process.env.ALLOWED_ORIGIN || '*' }));
app.use(express.json({ limit: '100kb' }));
app.use(express.static('.'));

app.post('/api/analyze', rateLimiter, async (req, res) => {
  const { transcript } = req.body;
  if (!transcript || typeof transcript !== 'string' || transcript.trim().length === 0)
    return res.status(400).json({ error: 'transcript is required.' });
  const trimmed = transcript.trim();
  if (trimmed.length > MAX_CHARS)
    return res.status(400).json({ error: `transcript too long (max ${MAX_CHARS} characters).` });

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'Service not configured. Contact the site owner.' });

  const prompt = `You are an expert English pronunciation and grammar coach.
Analyze the given English text (transcribed from a learner's speech) and return a JSON object ONLY - no markdown, no backticks, no extra text.

Return exactly this structure:
{
  "score": <integer 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "pronunciation_issues": ["<issue 1>", "<issue 2>"],
  "corrected_sentence": "<grammatically corrected full text>",
  "grammar_issues": ["<grammar issue with brief explanation>"],
  "tips": ["<actionable tip 1>", "<actionable tip 2>", "<tip 3>"]
}

Scoring: 90-100 near-native, 70-89 good, 50-69 intermediate, 30-49 beginner, 0-29 needs work.
If grammar is perfect, say so in grammar_issues. Always give pronunciation tips.

Analyze this English learner's speech:

"${trimmed}"`;

  const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash-lite';
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${apiKey}`;

  try {
    const upstream = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.3, maxOutputTokens: 1024 },
      }),
    });
    if (!upstream.ok) {
      const err = await upstream.json().catch(() => ({}));
      console.error('Gemini error:', err);
      if (upstream.status === 429) return res.status(429).json({ error: 'Service is busy. Please try again in a moment.' });
      return res.status(502).json({ error: 'Analysis service unavailable. Please try again.' });
    }
    const data  = await upstream.json();
    const raw   = data.candidates?.[0]?.content?.parts?.[0]?.text || '';
    const clean = raw.replace(/```json|```/g, '').trim();
    res.json(JSON.parse(clean));
  } catch (err) {
    console.error('Server error:', err);
    res.status(500).json({ error: 'Something went wrong. Please try again.' });
  }
});

app.get('/api/health', (_, res) => res.json({ status: 'ok', model: process.env.GEMINI_MODEL || 'gemini-2.5-flash-lite' }));

app.listen(PORT, () => {
  console.log(`PronounceAI running -> http://localhost:${PORT}`);
  console.log(`  Model: ${process.env.GEMINI_MODEL || 'gemini-2.5-flash-lite'} (Gemini free tier)`);
  console.log(`  Rate limit: ${RATE_LIMIT} req / ${RATE_WINDOW_MS / 60000} min per IP`);
});
