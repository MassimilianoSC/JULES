/*  chat/chat-state.js
    ──────────────────────────────────────────────────────────────────────────
    Stato reattivo (pure JS) della chat AI‑News.
    Non ha dipendenze DOM; altri moduli (renderer, ws‑handlers, comment‑manager)
    lo importano per leggere o mutare i dati.
*/
const _state = {
  newsId        : null,          // string | null – viene impostato all'init
  comments      : new Map(),     // Map<commentId, commentObj>
  likeState     : new Map(),     // Map<commentId, Set<userId>>
  typingState   : new Map(),     // Map<userId, lastPingMs>
  unreadCounter : 0,             // per futuri badge
};

const TYPING_COOLDOWN = 1_000;                // 1 s

/* ─── util ────────────────────────────────────────────── */
function _assert(cond, msg) {
  if (!cond) throw new Error('[chat‑state] ' + msg);
}

// ––– getter / setter ––––––––––––––––––––––––––––––––––––––––––––––––––––– //
function init(newsId, initialComments = []) {
  _assert(newsId, 'newsId is required');
  _assert(Array.isArray(initialComments), 'initialComments must be an array');

  _state.newsId   = newsId;
  _state.comments.clear();
  _state.likeState.clear();
  _state.typingState.clear();
  initialComments.forEach(c => _state.comments.set(c._id, c));
}

function addComment(c) {
  _state.comments.set(c._id, c);
}

function removeComment(commentId) {
  _state.comments.delete(commentId);
  _state.likeState.delete(commentId);
}

function updateLike(commentId, likesArr) {
  _state.likeState.set(commentId, new Set(likesArr));
}

function setTyping(userId, flag = true) {
  if (!flag) { _state.typingState.delete(userId); return; }

  const now  = Date.now();
  const last = _state.typingState.get(userId);
  if (last && now - last < TYPING_COOLDOWN) return;   // debounce

  _state.typingState.set(userId, now);
}

/** Pulizia automatica indicatori "sta scrivendo" > `olderThan` ms */
function cleanupTypingState(olderThan = 3_000) {
  const now = Date.now();
  for (const [uid, ts] of _state.typingState) {
    if (now - ts > olderThan) _state.typingState.delete(uid);
  }
}

/* ----- Stats Management ------------------------------------------ */
// Rimuoviamo la manipolazione DOM da qui. Se necessario, chi chiama questa logica
// (o un watcher sullo stato se fosse un sistema reattivo più complesso)
// dovrebbe emettere un evento per dom-renderer.
// export function updateStats(newsId, stats) {
//   if (!newsId || !stats) return;
  
//   // Aggiorna i contatori nell'UI
//   Object.entries(stats).forEach(([key, value]) => {
//     const counter = document.querySelector(`#${key}-${newsId} .stats-count`);
//     if (counter) counter.textContent = value;
//   });
// }

// ––– API pubblica –––––––––––––––––––––––––––––––––––––––––––––––––––––––– //
export default {
  /** Lettura diretta (read‑only) */
  get state()            { return _state; },
  /** Reset + caricamento commenti iniziali */
  init,
  /** Mutazioni granulari */
  addComment,
  removeComment,
  updateLike,
  setTyping,
  cleanupTypingState,
  // updateStats, // Rimosso dall'export pubblico, la gestione UI va a dom-renderer
};

// Removed bootstrapChat and deleteComment functions from here as they are
// either redundant or their responsibilities belong to other modules like
// comment-manager.js (for API calls) or ws-handlers.js (for WS messages).