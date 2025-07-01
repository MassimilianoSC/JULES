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
      if (!res.ok) throw new Error(res.statusText);
    })
    .catch(e => {
      log.error('Errore durante il tentativo di eliminazione del commento:', { commentId, newsId, error: e });
      alert('Errore durante l\'eliminazione del commento.');
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
  // Prima carichiamo le statistiche
  fetch(`/api/ai-news/${newsId}/stats`)
    .then(response => {
      if (!response.ok) throw new Error(`Errore HTTP stats: ${response.status}`);
      return response.json();
    })
    .then(stats => {
      log.debug(`Statistiche ricevute per ${newsId}:`, stats);
      const badge = document.querySelector(`#comments-badge-${newsId}`);
      if (badge) {
        badge.textContent = stats.comments;
        badge.classList.toggle('hidden', stats.comments === 0);
      }
      log.debug(`Caricamento commenti effettivi per ${newsId}...`);
      return fetch(`/api/ai-news/${newsId}/comments`);
    })
    .then(response => {
      if (!response.ok) throw new Error(`Errore HTTP commenti: ${response.status}`);
      return response.json();
    })
    .then(data => {
      log.debug(`Commenti ricevuti per ${newsId}:`, data.items?.length || 0);
      const commentsList = document.querySelector(`#comments-list-${newsId}`);
      if (!commentsList) {
        log.error(`Elemento lista commenti #comments-list-${newsId} non trovato.`);
        return;
      }
      commentsList.innerHTML = '';
      const currentUserId = window.currentUserId || (chatState.state.user ? chatState.state.user._id : null);
      const currentUserRole = window.currentUserRole || (chatState.state.user ? chatState.state.user.role : null);

      data.items.forEach(comment => {
        // Assumiamo che 'newsId' sia disponibile in questo scope
        // e che 'user' (l'utente loggato) sia accessibile globalmente o tramite chatState
        const commentElement = buildCommentElement(comment, newsId, currentUserId, currentUserRole);
        commentsList.appendChild(commentElement);
      });

      // La gestione dei listener per i pulsanti (like, reply, delete) ora dovrebbe essere centralizzata
      // o gestita tramite delega eventi sull'elemento `commentsList` o un suo genitore,
      // invece di riattaccarli qui. Per ora, questa parte è omessa, assumendo che
      // il listener globale in questo file o la logica in dom-renderer/index gestirà i click.
      // Se i pulsanti like usano HTMX (come in _comment_item.html), HTMX li gestirà automaticamente.
      // Per i pulsanti reply e delete che usano data-attributes, il listener delegato esistente
      // in questo file dovrebbe continuare a funzionare.
    })
    .catch(error => {
      log.error('Errore nel caricamento dei commenti:', { newsId, error });
      // TODO: Mostrare un messaggio di errore all'utente nell'UI, es. con un toast
      // showToast({ title: "Errore Chat", body: "Impossibile caricare i commenti.", type: "error" });
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