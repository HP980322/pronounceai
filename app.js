// PronounceAI - app.js

let audioFile = null, mediaRecorder = null, audioChunks = [], recordedBlob = null;
let recordingInterval = null, audioCtx = null, analyserNode = null, animFrameId = null;
let isRecording = false, recordingSeconds = 0;

document.addEventListener('DOMContentLoaded', () => { setupDropZone(); drawFlatLine(); });

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', (tab==='upload'&&i===0)||(tab==='record'&&i===1)));
  document.getElementById('uploadPanel').classList.toggle('hidden', tab !== 'upload');
  document.getElementById('recordPanel').classList.toggle('hidden', tab !== 'record');
}

function setupDropZone() {
  const zone = document.getElementById('dropZone');
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('dragover'); if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]); });
}

function handleFile(file) {
  if (!file || !file.type.startsWith('audio/')) { showStatus('Please select an audio file (MP3, WAV, M4A, OGG, WEBM).', 'error'); return; }
  audioFile = file;
  document.getElementById('fileName').textContent = file.name + '  (' + formatSize(file.size) + ')';
  document.getElementById('fileChosen').classList.remove('hidden');
  clearStatus();
}

function clearFile() { audioFile = null; document.getElementById('fileInput').value = ''; document.getElementById('fileChosen').classList.add('hidden'); }
function formatSize(b) { return b > 1048576 ? (b/1048576).toFixed(1)+' MB' : Math.round(b/1024)+' KB'; }

async function toggleRecord() { isRecording ? stopRecording() : await startRecording(); }

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = []; recordedBlob = null; recordingSeconds = 0; isRecording = true;
    audioCtx = new AudioContext(); analyserNode = audioCtx.createAnalyser(); analyserNode.fftSize = 256;
    audioCtx.createMediaStreamSource(stream).connect(analyserNode); drawWaveform();
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
    mediaRecorder.onstop = () => {
      recordedBlob = new Blob(audioChunks, { type: 'audio/webm' });
      stream.getTracks().forEach(t => t.stop());
      if (audioCtx) { audioCtx.close(); audioCtx = null; }
      cancelAnimationFrame(animFrameId); drawFlatLine();
      document.getElementById('playbackBtn').disabled = false;
      document.getElementById('discardBtn').disabled = false;
      setRecordStatus('Recorded: ' + formatTime(recordingSeconds), false);
    };
    mediaRecorder.start(200);
    document.getElementById('recordBtn').classList.add('recording');
    document.getElementById('playbackBtn').disabled = true;
    document.getElementById('discardBtn').disabled = true;
    recordingInterval = setInterval(() => { recordingSeconds++; setRecordStatus('Recording... ' + formatTime(recordingSeconds), true); }, 1000);
    setRecordStatus('Recording... 0:00', true);
  } catch { showStatus('Microphone access denied. Please allow microphone permissions.', 'error'); }
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

function formatTime(s) { return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }

function drawWaveform() {
  const canvas = document.getElementById('waveform'), ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth, H = canvas.offsetHeight;
  canvas.width = W; canvas.height = H;
  const arr = new Uint8Array(analyserNode.frequencyBinCount);
  function draw() {
    animFrameId = requestAnimationFrame(draw);
    analyserNode.getByteTimeDomainData(arr);
    ctx.clearRect(0,0,W,H); ctx.beginPath(); ctx.strokeStyle='#e8c547'; ctx.lineWidth=1.5;
    arr.forEach((v,i) => { const x=i*(W/arr.length), y=(v/128)*(H/2); i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
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

function showStatus(msg, type='error') {
  document.getElementById('statusMsg').innerHTML = '<div class="status-msg '+type+'">'+(type==='error'?'Warning: ':'Info: ')+msg+'</div>';
}
function clearStatus() { document.getElementById('statusMsg').innerHTML = ''; }

async function analyze() {
  clearStatus();
  const text = document.getElementById('textOverride').value.trim();
  const hasAudio = audioFile || recordedBlob;
  if (!hasAudio && !text) { showStatus('Please upload or record audio, or paste text to analyze.', 'error'); return; }
  setAnalyzing(true);
  try {
    let transcript = text;
    if (!text && hasAudio) transcript = await transcribeAudio(audioFile || recordedBlob);
    if (!transcript) { showStatus('Could not auto-transcribe. Please paste your text in the box below.', 'error'); setAnalyzing(false); return; }
    showTranscript(transcript);
    const feedback = await getAnalysis(transcript);
    showFeedback(feedback);
  } catch (err) {
    showStatus('Error: ' + err.message, 'error'); console.error(err);
  } finally { setAnalyzing(false); }
}

function transcribeAudio(blob) {
  return new Promise(resolve => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return resolve('');
    const audio = new Audio(URL.createObjectURL(blob));
    const rec = new SR(); rec.lang='en-US'; rec.continuous=true; rec.interimResults=false;
    let result = '';
    rec.onresult = e => { for (let i=e.resultIndex;i<e.results.length;i++) if(e.results[i].isFinal) result+=e.results[i][0].transcript+' '; };
    rec.onend = () => resolve(result.trim()); rec.onerror = () => resolve(result.trim());
    audio.play().then(()=>rec.start()).catch(()=>resolve(''));
    audio.onended = () => setTimeout(()=>rec.stop(), 800);
  });
}

async function getAnalysis(transcript) {
  setLoadingText('Analyzing pronunciation and grammar...');
  const res = await fetch('/api/analyze', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({transcript}) });
  if (!res.ok) { const err = await res.json().catch(()=>({})); throw new Error(err.error||'Server error '+res.status); }
  return res.json();
}

function setAnalyzing(on) {
  document.getElementById('analyzeBtn').disabled = on;
  document.getElementById('analyzeBtn').textContent = on ? 'Analyzing...' : 'Analyze My English';
  document.getElementById('resultsArea').classList.remove('hidden');
  document.getElementById('loadingBlock').classList.toggle('hidden', !on);
  if (!on) document.getElementById('loadingBlock').classList.add('hidden');
}

function setLoadingText(msg) { const el=document.querySelector('.loading-text'); if(el) el.textContent=msg; }

function showTranscript(text) {
  document.getElementById('transcriptSection').style.display='';
  const box=document.getElementById('transcriptBox'); box.textContent=text; box.classList.remove('placeholder');
}

function showFeedback(fb) {
  document.getElementById('feedbackSection').style.display='';
  const score=parseInt(fb.score)||0, el=document.getElementById('scoreDisplay');
  el.textContent=score+'/100';
  el.className='score-badge '+(score>=80?'score-high':score>=55?'score-mid':'score-low');
  document.getElementById('summaryText').textContent=fb.summary||'';
  fillList('pronList', fb.pronunciation_issues);
  document.getElementById('pronCard').style.display=(fb.pronunciation_issues&&fb.pronunciation_issues.length)?'':'none';
  document.getElementById('correctedText').textContent=fb.corrected_sentence||'';
  fillList('gramList', fb.grammar_issues);
  fillList('tipsList', fb.tips);
}

function fillList(id, items=[]) {
  const ul=document.getElementById(id); ul.innerHTML='';
  items.forEach(item => { const li=document.createElement('li'); li.textContent=item; ul.appendChild(li); });
}
