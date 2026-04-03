const API = 'http://localhost:8000';

let sessionId = null;
let isLocked  = false;

const $ = id => document.getElementById(id);

// ── Init ──────────────────────────────────────────────
async function startSession() {
  try {
    const res  = await fetch(`${API}/session/new`, { method: 'POST' });
    const data = await res.json();
    sessionId = data.session_id;
    $('sessionId').textContent = sessionId.slice(0, 8) + '...';
    resetUI();
  } catch (e) {
    addSystemMsg('Could not connect to server. Is it running?', 'warn');
  }
}

function resetUI() {
  $('messages').innerHTML = `
    <div class="welcome-msg">
      <div class="welcome-icon">◎</div>
      <p>Hello! Welcome to customer support.<br/>How can I help you today?</p>
    </div>`;
  $('infoIntent').textContent    = '—';
  $('infoLang').textContent      = '—';
  $('infoSentiment').textContent = '—';
  $('infoStatus').textContent    = 'Active';
  $('infoStatus').className      = 'info-val';
  $('slotsDisplay').innerHTML    = '<span class="slots-empty">No slots yet</span>';
  $('langBadge').textContent     = 'EN';
  $('escalationBanner').style.display = 'none';
  $('userInput').disabled        = false;
  $('sendBtn').disabled          = false;
  $('agentStatus').innerHTML     = '<span class="status-dot online"></span> Online';
  isLocked = false;
}

// ── Send Message ──────────────────────────────────────
async function sendMessage() {
  if (isLocked || !sessionId) return;
  const input = $('userInput');
  const text  = input.value.trim();
  if (!text) return;

  input.value = '';
  addMessage('user', text);
  setTyping(true);

  try {
    const res  = await fetch(`${API}/chat`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ session_id: sessionId, message: text }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Server error');
    }

    const data = await res.json();
    setTyping(false);
    addMessage('agent', data.reply, data);
    updateSidebar(data);

    if (data.escalate) {
      addSystemMsg('⚡ Escalating to human agent...', 'warn');
      $('escalationBanner').style.display = 'block';
      lockChat();
    } else if (data.resolved) {
      addSystemMsg('✓ Issue resolved', 'success');
      updateStatus('Resolved');
    }

  } catch (e) {
    setTyping(false);
    addSystemMsg(`Error: ${e.message}`, 'warn');
  }
}

// ── UI Helpers ────────────────────────────────────────
function addMessage(role, text, meta = null) {
  const msgs = $('messages');

  // Remove welcome message on first real message
  const welcome = msgs.querySelector('.welcome-msg');
  if (welcome) welcome.remove();

  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  div.appendChild(bubble);

  if (role === 'agent' && meta) {
    const metaRow = document.createElement('div');
    metaRow.className = 'msg-meta';
    metaRow.textContent = formatTime();

    if (meta.intent && meta.intent !== 'unclear') {
      const tag = document.createElement('span');
      tag.className = `intent-tag ${meta.resolved ? 'resolved' : meta.intent === 'complaint' ? 'complaint' : ''}`;
      tag.textContent = meta.intent.replace('_', ' ');
      metaRow.appendChild(tag);
    }
    div.appendChild(metaRow);
  }

  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addSystemMsg(text, type = '') {
  const msgs = $('messages');
  const div = document.createElement('div');
  div.className = `system-msg ${type}`;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

let typingEl = null;
function setTyping(on) {
  const msgs = $('messages');
  if (on) {
    typingEl = document.createElement('div');
    typingEl.className = 'msg agent';
    typingEl.innerHTML = `<div class="typing-bubble"><span></span><span></span><span></span></div>`;
    msgs.appendChild(typingEl);
    msgs.scrollTop = msgs.scrollHeight;
    $('userInput').disabled = true;
    $('sendBtn').disabled   = true;
    $('agentStatus').innerHTML = '<span class="status-dot typing"></span> Typing...';
  } else {
    if (typingEl) { typingEl.remove(); typingEl = null; }
    $('userInput').disabled = false;
    $('sendBtn').disabled   = false;
    $('userInput').focus();
    $('agentStatus').innerHTML = '<span class="status-dot online"></span> Online';
  }
}

function updateSidebar(data) {
  $('infoIntent').textContent    = data.intent    || '—';
  $('infoLang').textContent      = langLabel(data.language);
  $('infoSentiment').textContent = data.sentiment || '—';
  $('langBadge').textContent     = langLabel(data.language);

  const sentEl = $('infoSentiment');
  sentEl.className = data.sentiment === 'frustrated' ? 'info-val frustrated' : 'info-val';

  // Slots
  const slots = data.slots || {};
  const filled = Object.entries(slots).filter(([, v]) => v && v !== 'null');
  if (filled.length) {
    $('slotsDisplay').innerHTML = filled.map(([k, v]) =>
      `<div class="slot-item"><span class="slot-key">${k}</span><span class="slot-val">${v}</span></div>`
    ).join('');
  }
}

function updateStatus(label) {
  const el = $('infoStatus');
  el.textContent = label;
  el.className = 'info-val resolved';
}

function lockChat() {
  isLocked = true;
  $('userInput').disabled = true;
  $('sendBtn').disabled   = true;
  $('agentStatus').innerHTML = '<span class="status-dot"></span> Transferred';
}

function langLabel(code) {
  return { en: 'EN', hi: 'HI', hinglish: 'HI/EN' }[code] || (code || 'EN').toUpperCase();
}

function formatTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ── Hint clicks ───────────────────────────────────────
function fillInput(el) {
  $('userInput').value = el.textContent;
  $('userInput').focus();
}

// ── Event Listeners ───────────────────────────────────
$('sendBtn').addEventListener('click', sendMessage);
$('userInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
$('btnNewSession').addEventListener('click', startSession);

// ── Boot ──────────────────────────────────────────────
startSession();
