/* API globale richiamata dai template commento (reply, delete, send…) */

import bus         from '/static/js/core/event-bus.js';
import chatState   from './chat-state.js';
import { parseMentions } from './mentions.js';
// import { updateStats } from './chat-state.js'; // updateStats non è usata direttamente qui, ma da ws-handlers
import { buildCommentElement } from './dom-renderer.js'; // Importa la funzione di rendering
import logger from '/static/js/core/logger.js';

const log = logger.module('CommentMgr');

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
      if (!res.ok) {
        // Try to get a more specific error message from backend if available (e.g., JSON response)
        return res.text().then(text => { throw new Error(text || res.statusText); });
      }
      // No specific content needed on successful (204 No Content) delete usually
      // The DOM removal is handled by WebSocket event 'comment/delete' via ws-handlers.js -> chat:dom:remove
      log.info(`Commento ${commentId} eliminato (richiesta inviata). L'UI si aggiornerà tramite WebSocket.`);
      // Optionally, show a temporary success toast here if immediate feedback is desired before WS event
      // showToast({ title: "Commento", body: "Commento eliminato con successo.", type: "success" });
    })
    .catch(e => {
      log.error('Errore durante il tentativo di eliminazione del commento:', { commentId, newsId, error: e.message });
      if (typeof showToast === "function") {
        showToast({ title: "Errore Eliminazione", body: `Impossibile eliminare il commento: ${e.message}`, type: "error" });
      } else {
        alert(`Errore durante l'eliminazione del commento: ${e.message}`);
      }
    });
    return;
  }
});

function toggleComments(newsId) {
  log.debug(`Toggle commenti per newsId: ${newsId}`);
  const commentsSection = document.getElementById(`comments-section-${newsId}`);
  if (!commentsSection) {
    log.error(`Sezione commenti non trovata per news ${newsId}`);
    return;
  }
  
  if (commentsSection.classList.contains('hidden')) {
    log.debug(`Mostro sezione commenti e carico per newsId: ${newsId}`);
    commentsSection.classList.remove('hidden');
    loadComments(newsId);
    // dom-renderer ascolta chat:init, che dovrebbe essere emesso quando questa sezione
    // (che contiene comments-container-newsId) diventa visibile e pronta.
    // Assicuriamoci che chat:init venga emesso. Se non lo è, aggiungerlo qui o in loadComments.
    // Per ora, si assume che l'HTML parziale caricato da un potenziale HTMX trigger
    // o la struttura della pagina includa uno script che emette chat:init.
    // Se loadComments è il punto di ingresso principale, potremmo emettere chat:init qui.
    bus.emit('chat:init', { newsId });
  } else {
    log.debug(`Nascondo sezione commenti per newsId: ${newsId}`);
    commentsSection.classList.add('hidden');
    bus.emit('chat:destroy', { newsId: newsId, reason: 'toggled_off' });
  }
}

function loadComments(newsId) {
  log.info(`Caricamento commenti per newsId: ${newsId}`);
  const commentsList = document.querySelector(`#comments-list-${newsId}`);
  const commentsContainer = document.querySelector(`#comments-container-${newsId}`);

  if (!commentsList && commentsContainer) {
    // If the specific list isn't there but the main container is, it might be okay if HTMX loads the list structure.
    // For now, assume #comments-list-newsId is the direct target for JS rendering.
    log.error(`Elemento lista commenti #comments-list-${newsId} non trovato.`);
    // Optionally, show an error in the UI here.
    // For example: commentsContainer.innerHTML = '<p class="text-red-500">Errore: Impossibile caricare l\'area commenti.</p>';
    return;
  }
  if (!commentsList && !commentsContainer){
    log.error(`Contenitori commenti #comments-container-${newsId} e #comments-list-${newsId} non trovati.`);
    return;
  }

  // Show loading indicator
  if(commentsList) commentsList.innerHTML = '<p class="text-gray-500 p-4 text-center">Caricamento commenti...</p>';


  // Prima carichiamo le statistiche (questo potrebbe essere separato o combinato)
  fetch(`/api/ai-news/${newsId}/stats`)
    .then(response => {
      if (!response.ok) throw new Error(`Errore HTTP stats: ${response.status} ${response.statusText}`);
      return response.json();
    })
    .then(stats => {
      log.debug(`Statistiche ricevute per ${newsId}:`, stats);
      // Update stats display (e.g., badge count) - this might be handled by other dedicated functions too
      const badge = document.querySelector(`#comments-count-${newsId}`); // Assuming the comment count span has this ID now
      if (badge) {
        badge.textContent = stats.comments || 0;
      }
      // Fetch actual comments
      log.debug(`Caricamento commenti effettivi per ${newsId}...`);
      return fetch(`/api/ai-news/${newsId}/comments`); // This API endpoint should return the list of comments
    })
    .then(response => {
      if (!response.ok) throw new Error(`Errore HTTP commenti: ${response.status} ${response.statusText}`);
      return response.json(); // Expects { items: [], total_count: N, has_more: bool }
    })
    .then(data => {
      log.debug(`Commenti ricevuti per ${newsId}:`, data.items?.length || 0);
      if (!commentsList) return; // Guard clause if still not found (should not happen if check above is robust)

      commentsList.innerHTML = ''; // Clear loading message or old comments

      if (!data.items || data.items.length === 0) {
        commentsList.innerHTML = '<p class="text-gray-500 p-4 text-center">Nessun commento ancora.</p>';
        return;
      }

      const currentUserId = window.currentUserId || (chatState.state.user ? chatState.state.user._id : null);
      const currentUserRole = window.currentUserRole || (chatState.state.user ? chatState.state.user.role : null);

      data.items.forEach(comment => {
        const commentElement = buildCommentElement(comment, newsId, currentUserId, currentUserRole);
        commentsList.appendChild(commentElement);
      });

      // Handle "load more" button if present and `data.has_more` is true
      // (This logic would typically be in the template or handled by HTMX itself if API returns next page link)
    })
    .catch(error => {
      log.error('Errore nel caricamento dei commenti:', { newsId, error: error.message });
      if (commentsList) {
        commentsList.innerHTML = '<p class="text-red-500 p-4 text-center">Impossibile caricare i commenti. Riprova più tardi.</p>';
      }
      // Use the global showToast for user feedback
      // Ensure showToast is imported or available globally if used here.
      // For now, assuming it's available via other imports or global scope.
      if (typeof showToast === "function") {
        showToast({ title: "Errore Chat", body: "Impossibile caricare i commenti.", type: "error" });
      } else {
        console.warn("showToast function not available for error display in comment-manager.")
      }
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

function showReplyForm(commentId, newsId) { // newsId era implicito da chatState prima, ora lo passiamo
  const commentElement = document.getElementById(`comment-${commentId}`);
  if (!commentElement) return;

  const authorName = commentElement.querySelector('.font-medium.text-gray-900')?.textContent || 'commento';

  // Emetti un evento per far gestire il rendering del form a dom-renderer
  bus.emit('chat:display:replyForm', {
    commentId,
    newsId, // newsId è necessario per l'azione di invio
    parentAuthorName: authorName
  });
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
  send, // Esportata per essere usata da index.js e potenzialmente dal form di risposta in dom-renderer
  shareNews,
  updatePreview,
  togglePreview,
  toggleReplies,
  toggleComments,
  loadComments,
  showReplyForm,
  toggleEmojiPicker
};

// Ascolta l'evento per inviare una risposta, emesso da dom-renderer.js
bus.on('chat:send:reply', ({ newsId, parentId, content }) => {
  // Crea una textarea fittizia o recupera il riferimento se necessario,
  // oppure modifica la funzione 'send' per accettare direttamente il contenuto.
  // Per ora, creiamo una textarea fittizia per compatibilità con la firma di 'send'.
  const tempTextarea = { value: content };
  send(newsId, tempTextarea, parentId);
});