// PronounceAI v2 - app.js
// Backend: FastAPI + Whisper (local) + LanguageTool (local)

let currentTab = 'upload';
let audioFile = null, mediaRecorder = null, audioChunks = [], recordedBlob = null;
let recordingInterval = null, audioCtx = null, analyserNode = null, animFrameId = null;
let isRecording = false, recordingSeconds = 0;

document.addEventListener('DOMContentLoaded', () => {
  setupDropZone();
  drawFlatLine();
});

// ── Tabs ──────────────────────────────────────
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['upload','record','text'][i] === tab);
  });
  document.getElementById('uploadPanel').classList.toggle('hidden', tab !== 'upload');
  document.getElementById('recordPanel').classList.toggle('hidden', tab !== 'record');
  document.getElementById('textPanel').classList.toggle('hidden', tab !== 'text');
}

// ── File Upload ───────────────────────────────
function setupDropZone() {
  const zone = document.getElementById('dropZone');
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
}

function handleFile(file) {
  if (!file || !file.type.startsWith('audio/')) { showStatus('Please select an audio file.', 'error'); return; }
  audioFile = file;
  document.getElementById('fileName').textContent = file.name + '  (' + fmt(file.size) + ')';
  document.getElementById('fileChosen').classList.remove('hidden');
  clearStatus();
}

function clearFile() {
  audioFile = null;
  document.getElementById('fileInput').value = '';
  document.getElementById('fileChosen').classList.add('hidden');
}

function fmt(b) { return b > 1048576 ? (b/1048576).toFixed(1)+' MB' : Math.round(b/1024)+' KB'; }

// ── Recording ─────────────────────────────────
async function toggleRecord() { isRecording ? stopRecording() : await startRecording(); }

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = []; recordedBlob = null; recordingSeconds = 0; isRecording = true;
    audioCtx = new AudioContext();
    analyserNode = audioCtx.createAnalyser(); analyserNode.fftSize = 256;
    audioCtx.createMediaStreamSource(stream).connect(analyserNode);
    drawWaveform();
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
    mediaRecorder.onstop = () => {
      recordedBlob = new Blob(audioChunks, { type: 'audio/webm' });
      stream.getTracks().forEach(t => t.stop());
      if (audioCtx) { audioCtx.close(); audioCtx = null; }
      cancelAnimationFrame(animFrameId); drawFlatLine();
      document.getElementById('playbackBtn').disabled = false;
      document.getElementById('discardBtn').disabled = false;
      setRecordStatus('Recorded: ' + fmtTime(recordingSeconds), false);
    };
    mediaRecorder.start(200);
    document.getElementById('recordBtn').classList.add('recording');
    document.getElementById('playbackBtn').disabled = true;
    document.getElementById('discardBtn').disabled = true;
    recordingInterval = setInterval(() => {
      recordingSeconds++;
      setRecordStatus('Recording... ' + fmtTime(recordingSeconds), true);
    }, 1000);
    setRecordStatus('Recording... 0:00', true);
  } catch { showStatus('Microphone access denied.', 'error'); }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  clearInterval(recordingInterval); isRecording = false;
  document.getElementById('recordBtn').classList.remove('recording');
}

function playRecording() { if (recordedBlob) new Audio(URL.createObjectURL(recordedBlob)).play(); }

function discardRecording() {
  recordedBlob = null; audioChunks = [];
  document.getElementById('playbackBtn').disabled = true;
  document.getElementById('discardBtn').disabled = true;
  setRecordStatus('Click to start recording', false); drawFlatLine();
}

function setRecordStatus(msg, active) {
  const el = document.getElementById('recordStatus');
  el.textContent = msg; el.className = 'record-status' + (active ? ' active' : '');
}

function fmtTime(s) { return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }

// ── Waveform ──────────────────────────────────
function drawWaveform() {
  const canvas = document.getElementById('waveform'), ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth, H = canvas.offsetHeight;
  canvas.width = W; canvas.height = H;
  const arr = new Uint8Array(analyserNode.frequencyBinCount);
  function draw() {
    animFrameId = requestAnimationFrame(draw);
    analyserNode.getByteTimeDomainData(arr);
    ctx.clearRect(0,0,W,H); ctx.beginPath();
    ctx.strokeStyle = '#e8c547'; ctx.lineWidth = 1.5;
    arr.forEach((v,i) => { const x=i*(W/arr.length),y=(v/128)*(H/2); i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
    ctx.stroke();
  }
  draw();
}

function drawFlatLine() {
  const canvas = document.getElementById('waveform'); if (!canvas) return;
  const ctx = canvas.getContext('2d'), W = canvas.offsetWidth||600, H = canvas.offsetHeight||48;
  canvas.width=W; canvas.height=H; ctx.clearRect(0,0,W,H);
  ctx.beginPath(); ctx.strokeStyle='#2a2f42'; ctx.lineWidth=1.5;
  ctx.moveTo(0,H/2); ctx.lineTo(W,H/2); ctx.stroke();
}

// ── Status ────────────────────────────────────
function showStatus(msg, type='error') {
  document.getElementById('statusMsg').innerHTML =
    '<div class="status-msg '+type+'">'+(type==='error'?'&#9888; ':'')+msg+'</div>';
}
function clearStatus() { document.getElementById('statusMsg').innerHTML = ''; }

// ── Analyze ───────────────────────────────────
async function analyze() {
  clearStatus();
  const textVal = document.getElementById('textInput')?.value.trim();
  const hasAudio = audioFile || recordedBlob;

  if (currentTab === 'text' && !textVal) { showStatus('Please enter some text to analyze.', 'error'); return; }
  if (currentTab !== 'text' && !hasAudio) { showStatus('Please upload or record audio first.', 'error'); return; }

  setAnalyzing(true);
  try {
    let data;
    if (currentTab === 'text') {
      setLoading('Checking grammar with LanguageTool...');
      const res = await fetch('/api/analyze-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: textVal }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Server error');
      data = await res.json();
    } else {
      setLoading('Transcribing with Whisper (this may take 10-30s)...');
      const blob = audioFile || recordedBlob;
      const formData = new FormData();
      formData.append('file', blob, blob.name || 'recording.webm');
      const res = await fetch('/api/analyze-audio', { method: 'POST', body: formData });
      if (!res.ok) throw new Error((await res.json()).detail || 'Server error');
      data = await res.json();
    }
    renderResults(data);
  } catch (err) {
    showStatus('Error: ' + err.message, 'error');
    console.error(err);
  } finally { setAnalyzing(false); }
}

function setAnalyzing(on) {
  const btn = document.getElementById('analyzeBtn');
  btn.disabled = on;
  btn.textContent = on ? 'Analyzing...' : '\u2726 Analyze My English';
  document.getElementById('resultsArea').classList.remove('hidden');
  document.getElementById('loadingBlock').classList.toggle('hidden', !on);
  if (!on) document.getElementById('loadingBlock').classList.add('hidden');
}

function setLoading(msg) {
  const el = document.getElementById('loadingText'); if (el) el.textContent = msg;
}

function renderResults(data) {
  // Transcript
  if (data.transcript) {
    document.getElementById('transcriptSection').style.display = '';
    document.getElementById('transcriptBox').textContent = data.transcript;
  }

  document.getElementById('feedbackSection').style.display = '';

  // Score
  const score = parseInt(data.score) || 0;
  const el = document.getElementById('scoreDisplay');
  el.textContent = score + '/100';
  el.className = 'score-badge ' + (score >= 80 ? 'score-high' : score >= 55 ? 'score-mid' : 'score-low');

  document.getElementById('summaryText').textContent = data.summary || '';

  // Pronunciation
  fillList('pronList', data.pronunciation_issues);
  document.getElementById('pronCard').style.display =
    (data.pronunciation_issues && data.pronunciation_issues.length) ? '' : 'none';

  // Grammar
  document.getElementById('correctedText').textContent = data.corrected_sentence || data.transcript || '';
  fillList('gramList', data.grammar_issues);

  // Tips
  fillList('tipsList', data.tips);
}

function fillList(id, items = []) {
  const ul = document.getElementById(id); ul.innerHTML = '';
  (items || []).forEach(item => {
    const li = document.createElement('li'); li.textContent = item; ul.appendChild(li);
  });
}
