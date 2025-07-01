/* API globale richiamata dai template commento (reply, delete, send…) */

import bus         from '/static/js/core/event-bus.js';
import chatState   from './chat-state.js';
import { parseMentions } from './mentions.js';
import { updateStats } from './chat-state.js';

// Utility per il tempo relativo
function timeAgo(date) {
  const seconds = Math.floor((new Date() - new Date(date)) / 1000);
  const intervals = {
    anno: 31536000,
    mese: 2592000,
    settimana: 604800,
    giorno: 86400,
    ora: 3600,
    minuto: 60,
    secondo: 1
  };
  for (let [unit, secondsInUnit] of Object.entries(intervals)) {
    const interval = Math.floor(seconds / secondsInUnit);
    if (interval >= 1) {
      return `${interval} ${unit}${interval > 1 ? 'i' : ''} fa`;
    }
  }
  return 'adesso';
}

// Delega eventi per i commenti
document.addEventListener('click', e => {
  // Toggle commenti
  const toggleBtn = e.target.closest('.comments-toggle');
  if (toggleBtn) {
    const newsId = toggleBtn.dataset.newsId;
    toggleComments(newsId);
    return;
  }

  // Reply button
  const replyBtn = e.target.closest('.reply-button');
  if (replyBtn) {
    const { commentId, newsId } = replyBtn.dataset;
    showReplyForm(commentId, newsId);
    return;
  }

  // Toggle replies
  const toggleRepliesBtn = e.target.closest('.toggle-replies');
  if (toggleRepliesBtn) {
    const { commentId, newsId } = toggleRepliesBtn.dataset;
    toggleReplies(commentId, newsId);
    return;
  }

  // Delete comment
  const deleteBtn = e.target.closest('.delete-comment');
  if (deleteBtn) {
    const { commentId, newsId } = deleteBtn.dataset;
    if (!confirm('Eliminare il commento?')) return;
    
    fetch(`/api/ai-news/${newsId}/comments/${commentId}`, {
      method: 'DELETE',
      credentials: 'include'
    })
    .then(res => {
      if (!res.ok) throw new Error(res.statusText);
    })
    .catch(e => {
      console.error('[deleteComment] errore:', e);
      alert('Errore durante l\'eliminazione');
    });
    return;
  }
});

function toggleComments(newsId) {
  const commentsSection = document.getElementById(`comments-section-${newsId}`);
  if (!commentsSection) {
    console.error(`Sezione commenti non trovata per news ${newsId}`);
    return;
  }
  
  if (commentsSection.classList.contains('hidden')) {
    commentsSection.classList.remove('hidden');
    loadComments(newsId);
  } else {
    commentsSection.classList.add('hidden');
  }
}

function loadComments(newsId) {
  // Prima carichiamo le statistiche
  fetch(`/api/ai-news/${newsId}/stats`)
    .then(response => response.json())
    .then(stats => {
      // Aggiorniamo il badge con il totale iniziale
      const badge = document.querySelector(`#comments-badge-${newsId}`);
      if (badge) {
        badge.textContent = stats.comments;
        badge.classList.toggle('hidden', stats.comments === 0);
      }
      
      // Poi carichiamo i commenti
      return fetch(`/api/ai-news/${newsId}/comments`);
    })
    .then(response => response.json())
    .then(data => {
      const commentsList = document.querySelector(`#comments-list-${newsId}`);
      if (!commentsList) {
        console.error(`Lista commenti non trovata per news ${newsId}`);
        return;
      }
      commentsList.innerHTML = data.items.map(comment => `
        <div id="comment-${comment._id}" class="bg-white rounded-lg shadow p-4">
          <div class="flex items-start space-x-3">
            <div class="flex-shrink-0">
              <img class="h-10 w-10 rounded-full" src="/static/img/avatar-default.png" alt="">
            </div>
            <div class="flex-1">
              <div class="flex items-center justify-between">
                <div class="text-sm font-medium text-gray-900">${comment.author?.name || 'Utente'}</div>
                <div class="text-xs text-gray-500">${timeAgo(comment.created_at)}</div>
              </div>
              <div class="mt-1 prose prose-sm max-w-none text-gray-800">${comment.content}</div>
              
              <!-- Reactions -->
              <div class="mt-2 flex items-center space-x-2">
                <button class="reaction-button text-gray-500 hover:text-gray-700"
                        data-comment-id="${comment._id}"
                        data-reaction="like">
                  <span class="reaction-count">${comment.reactions?.like || 0}</span>
                  <i class="fas fa-thumbs-up"></i>
                </button>
              </div>

              <!-- Reply button -->
              <button class="reply-button mt-2 text-sm text-gray-500 hover:text-gray-700"
                      data-comment-id="${comment._id}">
                Rispondi
              </button>

              <!-- Delete button -->
              ${comment.can_delete ? `
              <button data-action="delete" data-id="${comment._id}" 
                      class="ml-2 text-sm text-red-500 hover:text-red-700">
                Elimina
              </button>
              ` : ''}
            </div>
          </div>
        </div>
      `).join('');

      // Aggiungiamo i listener per i pulsanti di eliminazione
      commentsList.querySelectorAll('[data-action="delete"]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          if (!confirm('Eliminare il commento?')) return;
          
          const commentId = btn.dataset.id;
          try {
            const res = await fetch(`/api/ai-news/${newsId}/comments/${commentId}`, {
              method: 'DELETE',
              credentials: 'include'
            });
            if (!res.ok) throw new Error(await res.text());
          } catch (e) {
            console.error('[deleteComment] errore:', e);
            alert('Errore durante l\'eliminazione');
          }
        });
      });
    })
    .catch(error => {
      console.error('Errore nel caricamento dei commenti:', error);
    });
}

function send(newsId, textarea, replyTo = null) {
  const contentRaw = textarea.value.trim();
  if (!contentRaw) return;

  /* estrai menzioni per il backend */
  const { cleanText, mentions } = parseMentions(contentRaw);

  /* notifica al bus → ws‑handlers → backend fetch */
  bus.emit('chat:send', {
    newsId,
    replyTo,
    content : cleanText,
    mentions: mentions.map(m => m.id),
  });

  textarea.value = '';
}

function showReplyForm(commentId) {
  const el = document.getElementById(`reply-form-container-${commentId}`);
  if (!el) return;
  /* se esiste già non ricrearlo */
  if (el.firstChild) { el.classList.toggle('hidden'); return; }

  el.classList.remove('hidden');
  el.innerHTML = /* html */`
    <div class="flex gap-2 mt-2">
      <textarea class="flex-1 p-2 border rounded-lg" rows="1"
                placeholder="Rispondi…"></textarea>
      <button class="px-3 py-1 bg-blue-600 text-white rounded-lg">
        Invia
      </button>
    </div>`;
  const ta   = el.querySelector('textarea');
  const sendBtn = el.querySelector('button');
  sendBtn.onclick = () => send(chatState.state.newsId, ta, commentId);
  ta.focus();
}

/* ----- Share  ---------------------------------------------------- */
async function shareNews(newsId) {
  if (navigator.share) {
    const url = location.origin + '/ai-news/' + newsId;
    await navigator.share({ title: 'AI‑News', url });
  } else {
    await navigator.clipboard.writeText(location.href);
    alert('Link copiato negli appunti');
  }
}

/* ---------------------------------------------------------------
 * Preview & char‑counter
 * ------------------------------------------------------------- */
function updatePreview(textarea, newsId) {
  const max   = +textarea.getAttribute('maxlength') || 1_000;
  const left  = max - textarea.value.length;

  // contatore
  const counter = document.getElementById(`char-count-${newsId}`);
  if (counter) counter.textContent = left;

  // markdown preview (hidden se l'utente non l'ha aperta)
  const preview = document.getElementById(`preview-${newsId}`);
  if (preview && !preview.classList.contains('hidden') && window.marked) {
    preview.innerHTML = marked.parse(textarea.value.trim());
  }
}

/* ---------------------------------------------------------------
 * Toggle Preview & Emoji Picker
 * ------------------------------------------------------------- */
function togglePreview(newsId) {
  const form = document.querySelector(`#comment-form-${newsId}`);
  const editorContainer = form.querySelector('.editor-container');
  const previewContainer = form.querySelector('.preview-container');
  const toggleButton = form.querySelector('.preview-toggle-text');
  const isPreviewVisible = !previewContainer.classList.contains('hidden');
  
  editorContainer.classList.toggle('hidden');
  previewContainer.classList.toggle('hidden');
  toggleButton.textContent = isPreviewVisible ? 'Mostra Preview' : 'Mostra Editor';
  
  // Aggiorna preview se necessario
  if (!isPreviewVisible) {
    const textarea = form.querySelector('textarea');
    updatePreview(textarea, newsId);
  }
}

function toggleEmojiPicker(button) {
  const picker = button.closest('.comment-form').querySelector('.emoji-picker');
  if (picker) {
    picker.classList.toggle('hidden');
  }
}

/* ----------------------------------------------------------
 *  Toggle replies (apre o chiude la lista sotto il commento)
 * -------------------------------------------------------- */
function toggleReplies(commentId) {
  const wrapper = document.querySelector(`#replies-container-${commentId}`);
  if (!wrapper) return;
  wrapper.classList.toggle('hidden');
}

// Esporta le funzioni pubbliche
export {
  send,
  shareNews,
  updatePreview,
  togglePreview,
  toggleReplies,
  toggleComments,
  loadComments,
  showReplyForm,
  toggleEmojiPicker
}; 