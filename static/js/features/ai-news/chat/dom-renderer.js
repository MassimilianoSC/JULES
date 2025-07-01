/* features/ai-news/chat/dom-renderer.js
   Render "stile WhatsApp" + batch‑DOM per AI‑News Chat
   dipendenze: event‑bus, chat‑state
*/
import bus       from '/static/js/core/event-bus.js';
import chatState from './chat-state.js';

/* ────────────── helpers DOM ──────────────────────────────────────────── */
const qs   = (sel,  root=document) => root.querySelector(sel);
const qsa  = (sel,  root=document) => [...root.querySelectorAll(sel)];
const html = str  => { const t = document.createElement('template'); t.innerHTML = str.trim(); return t.content.firstChild; };

let pending = [];      // queue di patch DOM
let rafId   = null;

/* Dispatch batch alla prossima animation‑frame */
function schedule(updateFn) {
  pending.push(updateFn);
  if (!rafId) rafId = requestAnimationFrame(flush);
}
function flush() {
  rafId = null;
  pending.forEach(fn => { try { fn(); } catch(e){ console.error('[renderer]',e);} });
  pending = [];
}

/* Allineamento in base all'autore */
function applyBubbleStyles(el, isMine) {
  el.classList.add('flex','items-start','gap-3','mb-2','rounded-lg','px-2','py-1','max-w-[80%]');
  el.classList.toggle('ml-auto',  isMine);            // tailwind self msg → a destra
  el.classList.toggle('bg-emerald-100', isMine);
  el.classList.toggle('bg-white',       !isMine);
}

/* Scroll‑to‑bottom (solo se l'utente è già vicino al fondo) */
function smartScroll(container, deltaPx = 120) {
  const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < deltaPx;
  if (nearBottom) container.scrollTop = container.scrollHeight;
}

/* ────────────── event bus bindings ───────────────────────────────────── */
bus.on('chat:init', ({ newsId }) => {
  const wrap = qs(`#comments-container-${newsId}`);
  if (!wrap) return console.warn('[renderer] container non trovato');

  /* ------- add comment ------- */
  bus.on('chat:dom:add', c => schedule(() => {
    /* se già presente evita duplicati (race WS + htmx) */
    if (qs(`#msg-${c._id}`)) return;

    /* Clono un markup di base: uso template mini‑inline per velocità */
    const bubble = html(`<div id="msg-${c._id}"></div>`);
    bubble.innerHTML = /* html */`
      <div class="chat-meta flex items-center gap-2 mb-0.5 text-xs text-gray-500">
        <span class="font-medium text-gray-900">${c.author_name}</span>
        <span>${new Date(c.created_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>
      </div>
      <div class="chat-text whitespace-pre-wrap break-words">${c.content}</div>
    `;
    applyBubbleStyles(bubble, c.author_id === window.currentUserId);

    /* inserisco in fondo */
    wrap.appendChild(bubble);
    smartScroll(wrap);
  }));

  /* ------- like update ------- */
  bus.on('chat:dom:update-like', ({ id, likes, mine }) => schedule(() => {
    const node = qs(`#msg-${id} .like-counter`);
    if (node) node.textContent = likes;
    const ico  = qs(`#msg-${id} .like-icon`);
    if (ico)   ico.classList.toggle('text-blue-500', mine);
  }));

  /* ------- delete ------- */
  bus.on('chat:dom:remove', id => schedule(() => {
    const el = qs(`#msg-${id}`);
    if (el) el.remove();
  }));

  /* ------- typing indicator ------- */
  const typingBox = qs(`#typing-indicator-${newsId}`);
  bus.on('chat:dom:typing', ({ userId, isTyping }) => schedule(() => {
    if (!typingBox) return;
    typingBox.textContent = isTyping ? `${userId} sta scrivendo…` : '';
  }));
});

function renderComment(c) {
  const isMe   = c.author_id === window.currentUserId;
  const side   = isMe ? 'self-end bg-emerald-100 dark:bg-emerald-200/20'
                     : 'mr-auto bg-white shadow-sm dark:bg-slate-800';
  const align  = isMe ? 'text-right' : 'text-left';

  const wrapper = document.createElement('article');
  wrapper.dataset.id = c._id;
  wrapper.className  = `chat-message ${side} ${align}`;

  wrapper.innerHTML = /* html */ `
      <div class="whitespace-pre-line">${escapeHtml(c.content)}</div>
      <div class="chat-meta">${formatTime(c.created_at)}</div>
  `;
  return wrapper;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit'
  });
}

function renderDeleteButton(commentId) {
  return `
    <button 
      data-delete-comment-btn
      data-comment-id="${commentId}"
      class="flex items-center space-x-1 text-gray-500 hover:text-red-600 text-sm">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
      <span>Elimina</span>
    </button>
  `;
} 