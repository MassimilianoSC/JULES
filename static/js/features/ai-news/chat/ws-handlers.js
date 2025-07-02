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

      case 'comment/like_update': // Handles the new event from backend
        // Expected p.data: { news_id, comment_id, likes_count }
        if (p.data && p.data.news_id && p.data.comment_id && typeof p.data.likes_count !== 'undefined') {
            // Update local chat state - chatState.updateLike might need adjustment
            // if it expects a full list of likers instead of just the count.
            // For now, let's assume we primarily update the DOM via an event.
            // The user who performed the action already got an HTTP response to update their like button state.
            // This WS message is mainly for other users to see the count change.

            // chatState.updateLike(p.data.comment_id, p.data.likes_count); // This would need chatState to be adapted

            eventBus.emit('chat:dom:update_like', {
              newsId: p.data.news_id,
              commentId: p.data.comment_id,
              likesCount: p.data.likes_count
              // isLikedByCurrentUser is not sent via WS for other users,
              // their like button state (visual fill) won't change unless they also liked it.
            });
        } else {
            console.error('[ws-handlers] Payload comment/like_update malformato:', p.data);
        }
        break;

      case 'typing': // p.data dovrebbe essere { newsId: ..., userId: ..., userName: ..., isTyping: true/false }
        if (p.data && p.data.newsId && p.data.userId !== undefined && p.data.isTyping !== undefined && p.data.userName) {
            chatState.setTyping(p.data.userId, p.data.isTyping); // Assuming setTyping stores based on userId
            eventBus.emit('chat:dom:typing', {
              newsId: p.data.newsId,
              userId : p.data.userId,
              userName: p.data.userName, // Pass userName for display
              isTyping: p.data.isTyping
            });
        } else {
            console.error('[ws-handlers] Payload typing malformato:', p.data);
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