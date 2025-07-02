/* Entry‑point del pacchetto Chat AI‑News */

import './chat-state.js';       // importa per side‑effects (crea singleton)
import './ws-handlers.js';
import './dom-renderer.js';
import * as mentions from './mentions.js';
import '/static/js/features/ai-news/emoji-picker.js';  // già esistente

import { eventBus } from "/static/js/core/event-bus.js";
import { showToast } from "/static/js/features/notifications/toast.js";
import { 
  send,
  toggleComments, 
  showReplyForm,
  loadComments
} from "./comment-manager.js";

/* Bootstrap all'apertura pagina AI‑News */
document.addEventListener('DOMContentLoaded', () => {
  const newsId = document.body.dataset.newsId;
  if (!newsId) return;

  /* commenti iniziali sono già renderizzati dal server; passiamo solo id */
  eventBus.emit('chat:init', { newsId });

  /* quando si abbandona la pagina */
  window.addEventListener('beforeunload', () => eventBus.emit('chat:destroy'));
});

export function initAiNewsChat() {
  // Gestione commenti
  document.querySelectorAll('[data-comment-form]').forEach(form => {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const newsId = form.dataset.newsId;
      const textarea = form.querySelector('textarea');
      send(newsId, textarea);
    });
  });

  // Toggle visualizzazione commenti
  document.querySelectorAll('.comments-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const newsId = btn.dataset.newsId;
      toggleComments(newsId);
    });
  });

  // Gestione risposte
  document.querySelectorAll('[data-reply-btn]').forEach(btn => {
    btn.addEventListener('click', () => {
      const commentId = btn.dataset.commentId;
      const newsId = btn.closest('[data-news-id]')?.dataset.newsId || btn.dataset.newsId; // Try to get newsId from button or a parent
      if (!newsId) {
        console.error("newsId not found for reply button for comment:", commentId);
        return;
      }
      showReplyForm(commentId, newsId);
    });
  });
}

export { mentions }; 