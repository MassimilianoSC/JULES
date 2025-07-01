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

async function bootstrapChat() {
  try {
    const response = await fetch(`/api/ai-news/${currentNewsId}/comments?since=0`);
    if (!response.ok) throw new Error('Failed to fetch comments');
    
    const comments = await response.json();
    
    // Reality check: confronta il numero di commenti nel DOM con quelli nel DB
    const domComments = document.querySelectorAll('.chat-message').length;
    if (domComments !== comments.length) {
      // Se c'è discrepanza, sostituisci completamente la lista
      const commentsContainer = document.querySelector('#comments-container');
      commentsContainer.innerHTML = ''; // Pulisci il contenitore
      comments.forEach(comment => {
        const commentElement = renderComment(comment);
        commentsContainer.appendChild(commentElement);
      });
    }
  } catch (error) {
    console.error('Error during chat bootstrap:', error);
  }
}

// Assicuriamoci che ogni delete emetta sempre l'evento WS
async function deleteComment(commentId) {
  try {
    const response = await fetch(`/api/ai-news/comments/${commentId}`, {
      method: 'DELETE'
    });
    
    if (!response.ok) {
      if (response.status === 404) {
        // Se il commento non esiste più nel DB, rimuoviamolo comunque dal DOM
        const commentElement = document.querySelector(`[data-comment-id="${commentId}"]`);
        if (commentElement) {
          commentElement.remove();
        }
      }
      throw new Error('Failed to delete comment');
    }

    // Emettiamo sempre l'evento WS dopo una delete riuscita
    ws.send(JSON.stringify({
      type: 'comment/remove',
      data: { commentId }
    }));

  } catch (error) {
    console.error('Error deleting comment:', error);
  }
} 