/* features/ai-news/chat/dom-renderer.js
   Renderizza e gestisce il DOM per la chat AI-News.
   Utilizza un sistema di gestione dello stato (currentNewsId) per assicurare
   che gli aggiornamenti DOM siano applicati solo alla chat correntemente attiva.
   I listener di eventi del bus sono registrati a livello di modulo e filtrano
   gli eventi in base al currentNewsId.
   Dipendenze: event-bus, chat-state (per user info).
*/
import bus from '/static/js/core/event-bus.js';
import chatState from './chat-state.js'; // Utilizzato per ottenere info sull'utente corrente
import logger from '/static/js/core/logger.js';

const log = logger.module('DOMRender');

/* ────────────── VARIABILI DI STATO DEL MODULO ─────────────────────────── */
let currentNewsId = null; // ID della news attualmente visualizzata e gestita
let commentsWrap = null; // Riferimento al contenitore dei commenti (es. #comments-container-newsId)
let typingIndicatorEl = null; // Riferimento all'elemento per l'indicatore "sta scrivendo"
// let commentsBadgeEl = null; // Riferimento al badge per il conteggio dei commenti (se gestito qui)

/* ────────────── HELPERS DOM E UTILITIES ──────────────────────────────── */
const qs = (sel, root = document) => root.querySelector(sel);
// const qsa = (sel, root = document) => [...root.querySelectorAll(sel)]; // Non usato attualmente

let pendingRAF = []; // Coda di funzioni da eseguire nel prossimo requestAnimationFrame
let rafId = null;    // ID del requestAnimationFrame

/**
 * Schedula una funzione per essere eseguita nel prossimo ciclo di animazione.
 * Questo aiuta a raggruppare le modifiche al DOM per migliori performance.
 * @param {Function} updateFn La funzione che modifica il DOM.
 */
function schedule(updateFn) {
    pendingRAF.push(updateFn);
    if (!rafId) {
        rafId = requestAnimationFrame(flushPendingRAF);
    }
}

/**
 * Esegue tutte le funzioni in coda e pulisce la coda.
 */
function flushPendingRAF() {
    rafId = null;
    pendingRAF.forEach(fn => {
        try {
            fn();
        } catch (e) {
            log.error('Errore durante flushPendingRAF:', e);
        }
    });
    pendingRAF = [];
}

/**
 * Esegue lo scroll intelligente del contenitore verso il basso.
 * Solo se l'utente è già vicino al fondo.
 * @param {HTMLElement} container L'elemento contenitore.
 * @param {number} deltaPx La distanza dal fondo per attivare lo scroll.
 */
function smartScroll(container, deltaPx = 120) {
    if (!container) return;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < deltaPx;
    if (nearBottom) {
        container.scrollTop = container.scrollHeight;
    }
}

/**
 * Formatta un timestamp in una stringa oraria (HH:MM).
 * @param {number|string} timestamp Il timestamp da formattare.
 * @returns {string} L'ora formattata o una stringa vuota.
 */
function formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ────────────── COSTRUZIONE ELEMENTI DOM ─────────────────────────────── */

/**
 * Costruisce l'elemento DOM completo per un singolo commento o risposta.
 * @param {object} comment L'oggetto commento.
 * @param {string} activeNewsId L'ID della news per cui si sta costruendo (usato per data attributes).
 * @param {string} userId L'ID dell'utente corrente.
 * @param {string} userRole Il ruolo dell'utente corrente.
 * @returns {HTMLElement} L'elemento DOM del commento.
 */
function buildCommentElement(comment, activeNewsId, userId, userRole) {
    const commentId = comment._id;

    const mainDiv = document.createElement('div');
    mainDiv.className = 'flex items-start space-x-3 p-4 bg-white rounded-lg shadow-sm mb-3';
    mainDiv.id = `comment-${commentId}`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'flex-shrink-0';
    const avatarImg = document.createElement('img');
    avatarImg.className = 'h-10 w-10 rounded-full';
    avatarImg.src = (comment.author && comment.author.avatar) ? comment.author.avatar : '/static/img/avatar-default.png';
    avatarImg.alt = (comment.author && comment.author.name) ? comment.author.name : 'Utente';
    avatarDiv.appendChild(avatarImg);
    mainDiv.appendChild(avatarDiv);

    const contentDiv = document.createElement('div');
    contentDiv.className = 'flex-grow';

    const headerDiv = document.createElement('div');
    headerDiv.className = 'flex items-center space-x-2';
    const authorSpan = document.createElement('span');
    authorSpan.className = 'font-medium text-gray-900';
    authorSpan.textContent = (comment.author && comment.author.name) ? comment.author.name : 'Utente Anonimo';
    const dateSpan = document.createElement('span');
    dateSpan.className = 'text-sm text-gray-500';
    dateSpan.textContent = formatTime(comment.created_at);
    headerDiv.appendChild(authorSpan);
    headerDiv.appendChild(dateSpan);
    contentDiv.appendChild(headerDiv);

    const textDiv = document.createElement('div');
    textDiv.className = 'mt-1 text-sm text-gray-700 comment-content-display';
    textDiv.textContent = comment.content; // Sanitizzato a backend, textContent è sicuro
    contentDiv.appendChild(textDiv);

    const footerDiv = document.createElement('div');
    footerDiv.className = 'mt-2 flex items-center space-x-4 text-sm';

    const likeButton = document.createElement('button');
    likeButton.className = 'flex items-center space-x-1 text-gray-500 hover:text-blue-600 transition-colors like-btn';
    likeButton.dataset.commentId = commentId;
    likeButton.dataset.newsId = activeNewsId;
    likeButton.innerHTML = `
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"></path>
        </svg>
        <span class="like-count">${comment.likes_count || 0}</span>`; // Assumiamo likes_count
    footerDiv.appendChild(likeButton);

    if (!comment.parent_id) {
        const replyButton = document.createElement('button');
        replyButton.className = 'text-sm text-gray-500 hover:text-gray-700 reply-button';
        replyButton.dataset.replyBtn = ''; // Per targeting JS da comment-manager
        replyButton.dataset.commentId = commentId;
        replyButton.dataset.newsId = activeNewsId;
        replyButton.textContent = 'Rispondi';
        footerDiv.appendChild(replyButton);
    }

    if (userRole === 'admin' || userId === comment.author_id) {
        const deleteButton = document.createElement('button');
        deleteButton.className = 'ml-auto text-sm text-red-500 hover:text-red-700 delete-comment-btn'; // ml-auto per allineare a destra
        deleteButton.dataset.deleteCommentBtn = ''; // Per targeting JS da comment-manager
        deleteButton.dataset.commentId = commentId;
        deleteButton.dataset.newsId = activeNewsId;
        deleteButton.textContent = 'Elimina';
        footerDiv.appendChild(deleteButton);
    }
    contentDiv.appendChild(footerDiv);

    const replyFormContainer = document.createElement('div');
    replyFormContainer.id = `reply-form-container-${commentId}`;
    replyFormContainer.className = 'mt-3 hidden'; // Nascosto di default
    contentDiv.appendChild(replyFormContainer);

    if (!comment.parent_id && comment.replies_count && comment.replies_count > 0) {
        const repliesSectionDiv = document.createElement('div');
        repliesSectionDiv.className = 'replies-section mt-3';

        const toggleRepliesButton = document.createElement('button');
        toggleRepliesButton.className = 'toggle-replies text-sm text-blue-600 hover:text-blue-800';
        toggleRepliesButton.dataset.commentId = commentId;
        toggleRepliesButton.dataset.newsId = activeNewsId; // Per caricare le risposte
        toggleRepliesButton.textContent = `Mostra risposte (${comment.replies_count})`;

        repliesSectionDiv.appendChild(toggleRepliesButton);

        const repliesContainerDiv = document.createElement('div');
        repliesContainerDiv.id = `replies-container-${commentId}`;
        repliesContainerDiv.className = 'hidden ml-8 mt-2 space-y-2 border-l-2 border-gray-200 pl-4'; // Aggiunto pl-4 per indentazione
        repliesSectionDiv.appendChild(repliesContainerDiv);
        contentDiv.appendChild(repliesSectionDiv);
    }

    mainDiv.appendChild(contentDiv);
    return mainDiv;
}

// Esporta la funzione per poterla usare in comment-manager.js o altrove se necessario
// formatTime è locale, buildCommentElement è il principale esportato da questa sezione.
export { buildCommentElement };


/* ────────────── INIZIALIZZAZIONE E DISTRUZIONE CHAT ────────────────── */

/**
 * Inizializza lo stato del renderer per una specifica news.
 * Pulisce la chat precedente se presente.
 * @param {string} newsId L'ID della news da inizializzare.
 */
function initializeChat(newsId) {
    log.info(`Inizializzazione chat per newsId: ${newsId}. Current: ${currentNewsId}`);
    if (currentNewsId && currentNewsId !== newsId) {
        log.debug(`Distruzione chat precedente per ${currentNewsId} prima di inizializzare ${newsId}`);
        destroyChat();
    }

    currentNewsId = newsId;
    const containerSelector = `#comments-container-${currentNewsId}`;
    commentsWrap = qs(containerSelector);

    if (!commentsWrap) {
        log.warn(`Contenitore commenti '${containerSelector}' non trovato. La chat non funzionerà.`);
        currentNewsId = null; // Invalida se il contenitore non è pronto
        return;
    }
    // commentsWrap.innerHTML = ''; // NON pulire. Il wrapper contiene già la struttura statica (form, lista).
    // La logica di loadComments in comment-manager.js pulirà specificamente la comments-list.
    log.debug(`Contenitore commenti per ${currentNewsId} identificato.`);

    const typingIndicatorSelector = `#typing-indicator-${currentNewsId}`;
    typingIndicatorEl = qs(typingIndicatorSelector);
    if (typingIndicatorEl) {
        typingIndicatorEl.textContent = ''; // Pulisci indicatore
        log.debug(`Indicatore typing per ${currentNewsId} pulito.`);
    }

    log.info(`Chat inizializzata per ${currentNewsId}. Contenitore:`, commentsWrap);
}

/**
 * Pulisce lo stato del renderer e il DOM relativo alla chat corrente.
 * Chiamata prima di inizializzare una nuova chat o quando si lascia la pagina.
 */
function destroyChat() {
    log.info(`Distruzione chat per ${currentNewsId}`);
    if (commentsWrap) {
        commentsWrap.innerHTML = '';
        log.debug(`Contenitore commenti per ${currentNewsId} svuotato.`);
    }
    if (typingIndicatorEl) {
        typingIndicatorEl.textContent = '';
        log.debug(`Indicatore typing per ${currentNewsId} svuotato.`);
    }
    commentsWrap = null;
    typingIndicatorEl = null;
    log.info(`Chat per ${currentNewsId} distrutta. currentNewsId resettato.`);
    currentNewsId = null;
}

// Listener per eventi di navigazione HTMX per pulire la chat se non più pertinente
document.body.addEventListener('htmx:afterOnLoad', function () {
    log.debug('htmx:afterOnLoad event triggered on body.');
    if (currentNewsId) {
        const currentChatContainer = qs(`#comments-container-${currentNewsId}`);
        if (!currentChatContainer) {
            log.info(`[NAV] Il contenitore della chat per ${currentNewsId} non esiste più. Distruggo la chat.`);
            destroyChat();
        } else {
            log.debug(`[NAV] Il contenitore della chat per ${currentNewsId} esiste ancora.`);
        }
    }
});


/* ────────────── GESTORI EVENTI DEL BUS (Registrati a livello di modulo) ─ */

bus.on('chat:init', ({ newsId: initNewsId }) => {
    log.info(`Ricevuto chat:init per ${initNewsId}. Current active: ${currentNewsId}`);
    if (currentNewsId === initNewsId && commentsWrap) {
        log.debug(`Chat per ${initNewsId} apparentemente già inizializzata. Re-inizializzo per sicurezza.`);
        // Se la chat è già inizializzata per lo stesso newsId, potremmo volerla resettare o ignorare.
        // Per ora, la re-inizializziamo per garantire uno stato pulito.
    }
    initializeChat(initNewsId);
});

// Evento per indicare che l'utente sta lasciando la pagina/sezione della chat
// Questo dovrebbe essere emesso da un gestore di navigazione più globale o da azioni UI specifiche.
bus.on('chat:destroy', ({ newsId: destroyNewsId, reason } = {}) => {
    log.info(`Ricevuto chat:destroy per newsId: ${destroyNewsId || 'any'}. Reason: ${reason || 'N/A'}. Current active: ${currentNewsId}`);
    // Se viene fornito un newsId, distruggi solo se corrisponde a quello corrente.
    // Se non viene fornito newsId, distruggi la chat corrente, qualunque essa sia.
    if (destroyNewsId && destroyNewsId !== currentNewsId) {
        log.debug(`Richiesta di distruzione per ${destroyNewsId} ignorata, chat attiva è ${currentNewsId}.`);
        return;
    }
    if (!currentNewsId) {
        log.debug('Nessuna chat attiva da distruggere.');
        return;
    }
    destroyChat();
});


/* ------- AGGIUNTA COMMENTO ------- */
// payload: { commentData, newsId: eventNewsId }
bus.on('chat:dom:add', ({ commentData, newsId: eventNewsId }) => {
    if (eventNewsId !== currentNewsId || !commentsWrap) {
        log.warn(`chat:dom:add per ${eventNewsId} (commentId: ${commentData._id}) ignorato. Chat attiva: ${currentNewsId}. Contenitore: ${commentsWrap ? 'OK' : 'Non trovato'}`);
        return;
    }
    log.debug(`chat:dom:add: Aggiunta commento ${commentData._id} a news ${eventNewsId}`);

    schedule(() => {
        if (qs(`#comment-${commentData._id}`, commentsWrap)) { // Evita duplicati
            log.warn(`Commento ${commentData._id} già presente nel DOM. Aggiunta saltata.`);
            return;
        }

        const userId = chatState.state.user ? chatState.state.user._id : null;
        const userRole = chatState.state.user ? chatState.state.user.role : null;

        const commentElement = buildCommentElement(commentData, currentNewsId, userId, userRole);

        let parentDomContainer = commentsWrap; // Default al contenitore principale dei commenti
        if (commentData.parent_id) {
            // È una risposta, cerca il contenitore delle risposte del commento genitore
            parentDomContainer = qs(`#replies-container-${commentData.parent_id}`, commentsWrap);
            if (parentDomContainer) {
                 // Se il contenitore delle risposte era nascosto, mostriamolo
                if (parentDomContainer.classList.contains('hidden')) {
                    parentDomContainer.classList.remove('hidden');
                }
                // Potremmo anche voler mostrare la sezione "replies-section" se era nascosta
                const parentCommentNode = qs(`#comment-${commentData.parent_id}`, commentsWrap);
                 if (parentCommentNode) {
                    const repliesSection = parentCommentNode.querySelector('.replies-section');
                    if (repliesSection && repliesSection.classList.contains('hidden')) {
                         repliesSection.classList.remove('hidden');
                    }
                 }
            } else {
                console.warn(`[renderer] Contenitore risposte #replies-container-${commentData.parent_id} non trovato per ${commentData._id}. Aggiungo al wrapper principale come fallback (non ideale).`);
                parentDomContainer = commentsWrap; // Fallback, anche se non dovrebbe succedere con UI corretta
            }
        }

        if (parentDomContainer) {
            parentDomContainer.appendChild(commentElement);
            smartScroll(parentDomContainer.closest('.overflow-y-auto') || commentsWrap); // Scrolla il parente scrollabile più vicino o il wrap principale
        } else {
            // Questo caso dovrebbe essere raro se i contenitori sono sempre presenti.
            // console.warn(`[renderer] Contenitore DOM non trovato per il commento ${commentData._id} (parent: ${commentData.parent_id}) nella news ${currentNewsId}.`);
        }
    });
});

/* ------- AGGIORNAMENTO LIKE (ESEMPIO - da implementare completamente) ------- */
// payload: { commentId, newsId: eventNewsId, likesCount, isLikedByCurrentUser }
bus.on('chat:dom:update_like', ({ commentId, newsId: eventNewsId, likesCount }) => { // isLikedByCurrentUser removed from WS payload for others
    if (eventNewsId !== currentNewsId || !commentsWrap) {
        log.debug(`chat:dom:update_like for news ${eventNewsId} (comment ${commentId}) ignored. Active: ${currentNewsId}`);
        return;
    }
    log.debug(`chat:dom:update_like: Updating like count for comment ${commentId} in news ${eventNewsId} to ${likesCount}`);

    schedule(() => {
        const commentNode = qs(`#comment-${commentId}`, commentsWrap);
        if (!commentNode) {
            log.warn(`Comment node #comment-${commentId} not found for like update.`);
            return;
        }

        const likeCountSpan = commentNode.querySelector('.like-count');
        if (likeCountSpan) {
            likeCountSpan.textContent = likesCount;
        } else {
            log.warn(`.like-count span not found in comment ${commentId}.`);
        }

        // The visual state of the like button (e.g., filled icon, color) for other users
        // is not changed here, as that depends on their own like status.
        // Only the count is updated for everyone.
        // The user who clicked the button should have their button updated by the HTTP response of the like action.
    });
});

/* ------- RIMOZIONE COMMENTO ------- */
// payload: { commentId, newsId: eventNewsId, parentId (opzionale) }
bus.on('chat:dom:remove', ({ commentId, newsId: eventNewsId }) => {
    if (eventNewsId !== currentNewsId || !commentsWrap) return;

    schedule(() => {
        const el = qs(`#comment-${commentId}`, commentsWrap);
        if (el) {
            el.remove();
            // Se era un commento genitore con risposte, anche il suo contenitore di risposte è rimosso.
            // Se era una risposta, il conteggio sul genitore dovrebbe essere aggiornato da un altro evento.
        }
    });
});

/* ------- INDICATORE "STA SCRIVENDO" ------- */
// payload: { userId, userName, isTyping, newsId: eventNewsId }
bus.on('chat:dom:typing', ({ userName, isTyping, newsId: eventNewsId }) => {
    if (eventNewsId !== currentNewsId || !typingIndicatorEl) return;

    schedule(() => {
        typingIndicatorEl.textContent = isTyping ? `${userName} sta scrivendo…` : '';
    });
});

/* ------- AGGIORNAMENTO BADGE COMMENTI (globale o specifico) ------- */
// payload: { newsId, totalComments }
bus.on('chat:badge:update', ({ newsId: eventNewsId, totalComments }) => {
    // Questo potrebbe essere un evento che vogliamo gestire anche se non è currentNewsId,
    // se i badge sono visibili in una lista di news, per esempio.
    // Per ora, lo leghiamo a currentNewsId per semplicità, assumendo che il badge
    // sia solo sulla pagina della news attiva.
    // if (eventNewsId !== currentNewsId) return; // Commentato per potenziale uso globale

    const badge = qs(`#comments-badge-${eventNewsId}`); // Cerchiamo il badge specifico per eventNewsId
    if (badge) {
        schedule(() => {
            badge.textContent = totalComments;
            badge.classList.toggle('hidden', totalComments === 0 || !totalComments);
        });
    }
});


/* ------- AGGIORNAMENTO STATISTICHE GENERICO (es. per conteggio commenti totali) ------- */
// payload: { newsId: eventNewsId, stats: { comments: Y, ... } }
bus.on('chat:stats:update', ({ newsId: eventNewsId, stats }) => {
    if (eventNewsId !== currentNewsId) return; // Lega all'istanza chat corrente
    if (!stats || typeof stats.comments === 'undefined') return;

    // Questo potrebbe aggiornare un contatore di commenti visibile nell'header della chat, per esempio.
    // La logica del badge dei commenti nella navbar è gestita da 'chat:badge:update'.
    // Esempio: const totalCommentsDisplay = qs(`#chat-header-comment-count-${currentNewsId}`);
    // if (totalCommentsDisplay) schedule(() => totalCommentsDisplay.textContent = stats.comments);
});

/* ------- VISUALIZZAZIONE FORM DI RISPOSTA ------- */
// payload: { commentId, newsId: eventNewsId, parentAuthorName }
bus.on('chat:display:replyForm', ({ commentId, newsId: eventNewsId, parentAuthorName }) => {
    if (eventNewsId !== currentNewsId || !commentsWrap) return;

    schedule(() => {
        const formContainer = qs(`#reply-form-container-${commentId}`, commentsWrap);
        if (!formContainer) {
            console.warn(`[renderer] Contenitore form di risposta non trovato per ${commentId}`);
            return;
        }

        formContainer.innerHTML = ''; // Pulisci eventuale form precedente

        const formWrapper = document.createElement('div');
        formWrapper.className = 'flex gap-2 mt-2';

        const textarea = document.createElement('textarea');
        textarea.className = 'flex-1 p-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none';
        textarea.rows = 1; // Si espanderà con CSS o JS se necessario
        textarea.placeholder = `Rispondi a ${parentAuthorName || 'commento'}...`;

        const sendButton = document.createElement('button');
        sendButton.className = 'px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors';
        sendButton.textContent = 'Invia';

        sendButton.onclick = () => {
            if (textarea.value.trim()) {
                bus.emit('chat:send:reply', {
                    newsId: currentNewsId, // Usa currentNewsId per coerenza
                    parentId: commentId,
                    content: textarea.value.trim()
                });
                textarea.value = '';
                formContainer.classList.add('hidden'); // Nascondi dopo l'invio
                formContainer.innerHTML = ''; // Rimuovi il form dopo l'invio
            }
        };

        const cancelButton = document.createElement('button');
        cancelButton.className = 'px-3 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors';
        cancelButton.textContent = 'Annulla';
        cancelButton.onclick = () => {
            formContainer.classList.add('hidden');
            formContainer.innerHTML = '';
        };

        formWrapper.appendChild(textarea);
        formWrapper.appendChild(sendButton);
        formWrapper.appendChild(cancelButton);
        formContainer.appendChild(formWrapper);
        formContainer.classList.remove('hidden');
        textarea.focus();

        // Auto-resize textarea
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = `${textarea.scrollHeight}px`;
        });
    });
});

/* ------- AGGIORNAMENTO CONTEGGIO RISPOSTE SUL COMMENTO GENITORE ------- */
// payload: { parentId, newsId: eventNewsId, newCount }
bus.on('chat:dom:update_reply_count', ({ parentId, newsId: eventNewsId, newCount }) => {
    if (eventNewsId !== currentNewsId || !commentsWrap) return;

    schedule(() => {
        const parentCommentNode = qs(`#comment-${parentId}`, commentsWrap);
        if (!parentCommentNode) return;

        const toggleRepliesButton = parentCommentNode.querySelector('.toggle-replies');
        const repliesSection = parentCommentNode.querySelector('.replies-section');

        if (toggleRepliesButton) {
            toggleRepliesButton.textContent = `Mostra risposte (${newCount})`;
        }

        if (repliesSection) {
            if (newCount > 0) {
                repliesSection.classList.remove('hidden');
                // Non mostriamo automaticamente il repliesContainer, quello è compito del toggleRepliesButton
            } else {
                repliesSection.classList.add('hidden');
                const repliesContainer = qs(`#replies-container-${parentId}`, parentCommentNode);
                if (repliesContainer) repliesContainer.classList.add('hidden'); // Nascondi anche il contenitore effettivo
            }
        }
    });
});

// Le funzioni `applyBubbleStyles`, `renderComment`, `escapeHtml`, `renderDeleteButton`
// non sono più utilizzate direttamente poiché `buildCommentElement` centralizza la creazione
// e la sanitizzazione del contenuto è gestita a backend + textContent.
// Vengono rimosse per pulizia.