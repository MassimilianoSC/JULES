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

eventBus.on('ws:ai-news', p => { // p è il payload del messaggio WebSocket
  try {
    const { type } = p || {}; // p.type è 'comment/add', 'comment/delete', etc.
    if (!type) throw new Error('payload.type missing');

    switch (type) {
      case 'comment/add': // p.comment dovrebbe contenere news_id e parent_id (se è una risposta)
        chatState.addComment(p.data.comment); // Assumendo che il payload WS sia {type: 'comment/add', data: { news_id: ..., comment: {...} }}
        eventBus.emit('chat:badge:update', { newsId: p.data.news_id, totalComments: p.data.total_comments });
        eventBus.emit('chat:dom:add', { commentData: p.data.comment, newsId: p.data.news_id }); // Passa newsId
        break;

      case 'comment/delete':
        chatState.removeComment(p.data.comment_id);
        eventBus.emit('chat:dom:remove', { commentId: p.data.comment_id, newsId: p.data.news_id }); // Passa newsId
        eventBus.emit('chat:badge:update', { newsId: p.data.news_id, totalComments: p.data.total_comments });
        break;

      case 'reply/add':
        if (p.data && p.data.reply && p.data.parent_id && p.data.news_id) {
          chatState.addComment(p.data.reply);
          eventBus.emit('chat:dom:add', { commentData: p.data.reply, newsId: p.data.news_id }); // dom-renderer usa parent_id da commentData
          eventBus.emit('chat:dom:update_reply_count', {
            commentId: p.data.parent_id,
            newCount: p.data.parent_replies_count,
            newsId: p.data.news_id // Aggiunto newsId per coerenza, anche se dom-renderer potrebbe non usarlo qui
          });
        } else {
          console.error('[ws-handlers] Payload reply/add malformato:', p);
        }
        break;

      case 'reply/delete':
        if (p.data && p.data.reply_id && p.data.parent_id && p.data.news_id) {
          chatState.removeComment(p.data.reply_id);
          eventBus.emit('chat:dom:remove', { commentId: p.data.reply_id, newsId: p.data.news_id });
          eventBus.emit('chat:dom:update_reply_count', {
            commentId: p.data.parent_id,
            newCount: p.data.parent_replies_count,
            newsId: p.data.news_id // Aggiunto newsId
          });
        } else {
          console.error('[ws-handlers] Payload reply/delete malformato:', p);
        }
        break;

      case 'like': // p dovrebbe essere { type: 'like', newsId: ..., commentId: ..., likes: [...] }
        if (p.newsId && p.commentId && Array.isArray(p.likes)) {
            chatState.updateLike(p.commentId, p.likes);
            eventBus.emit('chat:dom:update-like', {
              id   : p.commentId,
              likes: p.likes.length,
              mine : p.likes.includes(window.currentUserId),
              newsId: p.newsId // Aggiunto newsId
            });
        } else {
            console.error('[ws-handlers] Payload like malformato:', p);
        }
        break;

      case 'typing': // p dovrebbe essere { type: 'typing', newsId: ..., userId: ..., isTyping: true/false }
        if (p.newsId && p.userId !== undefined && p.isTyping !== undefined) {
            chatState.setTyping(p.userId, p.isTyping);
            eventBus.emit('chat:dom:typing', {
              userId : p.userId,
              isTyping: p.isTyping,
              newsId: p.newsId // Aggiunto newsId
            });
        } else {
            console.error('[ws-handlers] Payload typing malformato:', p);
        }
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