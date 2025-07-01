/* ---------------------------------------------------------------
 * reality-check.js  – rimuove commenti "fantasma" in UI
 * ------------------------------------------------------------- */
import { bus } from '/static/js/core/event-bus.js';
import { renderComment } from './dom-renderer.js';    // se hai già la funzione

/**
 * Sincronizza la lista commenti con lo stato del DB.
 * - newsId  → id della news AI
 * - container → elemento UL/OL che contiene <article class="chat-message">
 */
export async function syncComments(newsId, container) {
  try {
    const res = await fetch(`/api/ai-news/${newsId}/comments?since=0`, {
      credentials: 'include'
    });
    if (!res.ok) throw new Error(await res.text());
    const serverComments = await res.json();     // [{_id, body, author, …}, …]

    /* --- build Set di id lato server + dom --------------------- */
    const idsServer = new Set(serverComments.map(c => c._id));
    const domNodes  = Array.from(container.querySelectorAll('[data-id]'));

    /* a) rimuovi nodi che non esistono più ---------------------- */
    domNodes.forEach(n => {
      if (!idsServer.has(n.dataset.id)) n.remove();
    });

    /* b) aggiungi quelli mancanti  ------------------------------ */
    const idsDom = new Set(
      Array.from(container.querySelectorAll('[data-id]')).map(n => n.dataset.id)
    );
    serverComments.forEach(c => {
      if (!idsDom.has(c._id)) {
        container.appendChild(renderComment(c));
      }
    });

    console.log('[DEBUG_AI_NEWS] reality‑check OK');
  } catch (err) {
    console.error('[DEBUG_AI_NEWS] reality‑check failed:', err);
  }
}

/* ---------------------------------------------------------------
 * auto‑bootstrap  (eseguito quando la chat viene inizializzata)
 * ------------------------------------------------------------- */
bus.on('chat:init', ({ newsId }) => {
  const list = document.getElementById(`comments-section-${newsId}`);
  if (list) syncComments(newsId, list);
}); 