/* features/ai-news/chat/ws-handlers.js
   Gestione eventi WebSocket per AI‑News Chat
   dipendenze: event‑bus, chat‑state
*/
import { eventBus } from '/static/js/core/event-bus.js';
import chatState from './chat-state.js';

/* Aliasing per leggibilità */
const state = chatState;

/* ── In arrivo dal backend ─────────────────────────────
   payload = {
     type      : 'comment' | 'like' | 'delete' | 'typing',
     comment   : {...},          // per type='comment'
     commentId : '...',          // per like/delete
     likes     : [userId, ...],  // per like
     userId    : '...',          // per typing
     isTyping  : true|false,     // per typing
  }
*/
function updateBadge(newsId, total) {
  const badge = document.querySelector(`#comments-badge-${newsId}`);
  if (badge) {
    badge.textContent = total;
    badge.classList.toggle('hidden', total === 0);
  }
}

eventBus.on('ws:ai-news', p => {
  try {
    const { type } = p || {};
    if (!type) throw new Error('payload.type missing');

    switch (type) {
      case 'comment/add':
        chatState.addComment(p.comment);
        updateBadge(p.news_id, p.total);
        eventBus.emit('chat:dom:add', p.comment);
        break;

      case 'comment/delete':
        chatState.removeComment(p.comment_id);
        document.querySelector(`[data-id="${p.comment_id}"]`)?.remove();
        updateBadge(p.news_id, p.total);
        break;

      case 'reply/add':
        // TODO: implementare se usiamo il contatore aggregato
        break;

      case 'reply/delete':
        // TODO: implementare se usiamo il contatore aggregato
        break;

      case 'like':
        chatState.updateLike(p.commentId, p.likes);
        eventBus.emit('chat:dom:update-like', {
          id   : p.commentId,
          likes: p.likes.length,
          mine : p.likes.includes(window.currentUserId),
        });
        break;

      case 'typing':
        chatState.setTyping(p.userId, p.isTyping);
        eventBus.emit('chat:dom:typing', {
          userId : p.userId,
          isTyping: p.isTyping,
        });
        break;

      default:
        console.warn('[ws-handlers] tipo non gestito:', type);
    }
  } catch (e) {
    console.error('[ws-handlers] bad payload', e, p);
  }
});

/* Garbage‑collection typing indicator – loop ogni 4 s */
let cleanupInterval;
eventBus.on('chat:init', () => {
  if (cleanupInterval) clearInterval(cleanupInterval);
  cleanupInterval = setInterval(() => chatState.cleanupTypingState(), 4_000);
});
eventBus.on('chat:destroy', () => cleanupInterval && clearInterval(cleanupInterval));

/* ────────────── init ───────────────────────────────────────────────── */
export function init(newsId) {
  /* carico stato iniziale */
  chatState.init(newsId);
  
  /* notifico UI */
  eventBus.emit('chat:init', { newsId });
} 