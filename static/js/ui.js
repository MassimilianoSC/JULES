// --- Funzione globale per pin/unpin card ---
window.togglePin = function(type, id, btn) {
  const isPinned = btn.classList.contains('pinned');
  const homeHighlightsElement = document.getElementById('home-page-highlights');
  const cardType = btn.closest('div').classList.contains('bg-pink-50') ? 'pink' :
                  btn.closest('div').classList.contains('bg-blue-50') ? 'blue' :
                  btn.closest('div').classList.contains('bg-violet-50') ? 'violet' :
                  btn.closest('div').classList.contains('bg-green-50') ? 'green' :
                  btn.closest('div').classList.contains('bg-yellow-50') ? 'yellow' : 'yellow';

  if (!isPinned) {
    fetch('/api/me/pins', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type, id})
    }).then(r => r.json()).then(data => {

      if (data.ok) {
        btn.classList.add('pinned');
        btn.classList.remove('text-slate-400');
        btn.classList.add(`text-${cardType}-400`);
        btn.innerText = '★';
        if (homeHighlightsElement && window.htmx) {
          htmx.ajax('GET', '/home/highlights/partial', {
            target: homeHighlightsElement,
            swap: 'outerHTML'
          });
        }
      }
    });
  } else {
    fetch(`/api/me/pins/${type}/${id}`, {method: 'DELETE'})
      .then(r => r.json()).then(data => {
        if (data.ok) {
          btn.classList.remove('pinned');
          btn.classList.remove(`text-${cardType}-400`);
          btn.classList.add('text-slate-400');
          btn.innerText = '☆';
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
        }
      });
  }
};

// Tutto il codice che accede al DOM dentro DOMContentLoaded

document.addEventListener('DOMContentLoaded', () => {
  // Inizializza le variabili globali per i permessi utente
  window.currentUserRole = document.body.dataset.userRole;
  window.currentUserId = document.body.dataset.userId;

  // Modal functionality
  // Mostra modale quando HTMX mette contenuto in #modal-body
  // e nascondi quando ricevi evento closeModal

  document.body.addEventListener('htmx:afterSwap', e => {
    if (e.detail.target && e.detail.target.id === 'modal-body') {
      const modalOverlay = document.getElementById('modal-overlay');
      if (modalOverlay) {
        modalOverlay.classList.remove('hidden');
      }
    }
  });

  // Hide modal when POST response triggers closeModal
  document.body.addEventListener('closeModal', () => {
    const modalOverlay = document.getElementById('modal-overlay');
    if (modalOverlay) {
      modalOverlay.classList.add('hidden');
    }
  });

  // Funzione globale per chiudere il modale (usata nei bottoni Annulla dei modali)
  window.closeModal = function () {
    const modalOverlay = document.getElementById('modal-overlay');
    if (modalOverlay) {
      modalOverlay.classList.add('hidden');
    }
  };
  document.body.addEventListener('closeModal', window.closeModal);

  // Make showDelete globally available
  window.showDelete = function (btn) {
    Swal.fire({
      title: 'Sei sicuro?',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Sì, elimina',
      cancelButtonText: 'Annulla',
    }).then((r) => {
      if (r.isConfirmed) btn.closest('form').requestSubmit();
    });
  };

  // --- WebSocket globale per notifiche e toast ---
  function connectWebSocket() {

    const wsHost = window.WS_HOST || location.host;
    window.ws = new WebSocket(
      (location.protocol === 'https:' ? 'wss://' : 'ws://') + wsHost + '/ws/notify'
    );
    window.ws.onopen = function() {};
    window.ws.onerror = function(e) {};
    window.ws.onclose = function(event) {};
    window.ws.onmessage = function(event) {
      console.log('[WS][LOG] Ricevuto messaggio WebSocket:', event.data);
      try {
        let payload = event.data;
        if (typeof payload === 'string') {
          try { payload = JSON.parse(payload); } catch (e) { return; }
        }
        // Loggo il payload decodificato
        console.log('[WS][LOG] Payload decodificato:', payload);
        // --- Gestione LINK ---
        if (payload.type === 'new_notification' && payload.data && payload.data.tipo === 'link') {
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (!homeHighlightsElement) {
            console.warn('[WS][LOG] home-page-highlights NON TROVATO nel DOM (link)');
          } else {
            console.log('[WS][LOG] home-page-highlights TROVATO nel DOM (link), lancio HTMX');
          }
          fetch('/notifiche/inline')
            .then(response => response.text())
            .then(html => {
              if (html.includes(payload.data.id)) {
                Toastify({
                  text: payload.data.message,
                  duration: 4000,
                  gravity: 'top',
                  position: 'right',
                  backgroundColor: 'linear-gradient(to right, #00b09b, #96c93d)'
                }).showToast();
              }
            });
          if (homeHighlightsElement && window.htmx) {
            console.log('[WS] Aggiorno highlights (link)');
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML',
              handler: function(xhr, target) {
                console.log('[WS] Risposta highlights (link):', xhr && xhr.responseText ? xhr.responseText : '');
                return xhr && xhr.responseText ? xhr.responseText : '';
              }
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshLinkBadgeEvent');
          }
        }
        if (payload.type === 'remove_link' && payload.data) {
          let msg = 'Link eliminato!';
          if (payload.data.title) {
            msg = `Link eliminato: "${payload.data.title}" (${payload.data.branch || ''})`;
          }
          Toastify({
            text: msg,
            duration: 4000,
            gravity: 'top',
            position: 'right',
            backgroundColor: 'linear-gradient(to right, #ef4444, #f87171)'
          }).showToast();
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
          const linksListElement = document.getElementById('links-list');
          if (linksListElement && window.htmx) {
            htmx.ajax('GET', '/links', {
              target: linksListElement,
              swap: 'outerHTML',
              select: '#links-list'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshLinkBadgeEvent');
          }
        }
        if (payload.type === 'update_link' && payload.data) {
          let msg = 'Link modificato!';
          if (payload.data.title) {
            msg = `Link modificato: "${payload.data.title}" (${payload.data.branch || ''})`;
            if (payload.data.consequence) {
              msg += `\n${payload.data.consequence}`;
            }
          }
          Toastify({
            text: msg,
            duration: 4000,
            gravity: 'top',
            position: 'right',
            backgroundColor: 'linear-gradient(to right, #fbbf24, #f59e42)'
          }).showToast();
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshLinkBadgeEvent');
          }
        }
        // --- Gestione CONTATTI ---
        if (payload.type === 'new_notification' && payload.data && payload.data.tipo === 'contatto') {
          if (payload.data.message && payload.data.message.includes('eliminato')) {
            Toastify({
              text: payload.data.message,
              duration: 4000,
              gravity: 'top',
              position: 'right',
              backgroundColor: 'linear-gradient(to right, #ef4444, #f87171)'
            }).showToast();
          } else if (payload.data.message && payload.data.message.includes('modificato')) {
            Toastify({
              text: payload.data.message + '\nI destinatari potrebbero essere cambiati.',
              duration: 4000,
              gravity: 'top',
              position: 'right',
              backgroundColor: 'linear-gradient(to right, #fbbf24, #f59e42)'
            }).showToast();
          } else {
            fetch('/notifiche/inline')
              .then(response => response.text())
              .then(html => {
                if (html.includes(payload.data.id)) {
                  Toastify({
                    text: payload.data.message,
                    duration: 4000,
                    gravity: 'top',
                    position: 'right',
                    backgroundColor: 'linear-gradient(to right, #00b09b, #96c93d)'
                  }).showToast();
                }
              });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshContattiBadgeEvent');
          }
        }
        if (payload.type === 'new_contact' && payload.data) {
          const contactsListElement = document.getElementById('contatti-list');
          if (contactsListElement && window.htmx) {
            htmx.ajax('GET', '/contatti', {
              target: contactsListElement,
              swap: 'outerHTML',
              select: '#contatti-list'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshContattiBadgeEvent');
          }
        }
        if (payload.type === 'update_contact_highlight' && payload.data) {
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshContattiBadgeEvent');
          }
        }
        if (payload.type === 'update_contact' && payload.data) {
          const contactsListElement = document.getElementById('contatti-list');
          if (contactsListElement && window.htmx) {
            htmx.ajax('GET', '/contatti', {
              target: contactsListElement,
              swap: 'outerHTML',
              select: '#contatti-list'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshContattiBadgeEvent');
          }
        }
        if (payload.type === 'remove_contact' && payload.data) {
          let msg = 'Contatto eliminato!';
          if (payload.data.title) {
            msg = `Contatto eliminato: "${payload.data.title}" (${payload.data.branch || ''})`;
          }
          Toastify({
            text: msg,
            duration: 4000,
            gravity: 'top',
            position: 'right',
            backgroundColor: 'linear-gradient(to right, #ef4444, #f87171)'
          }).showToast();
          const contactsListElement = document.getElementById('contatti-list');
          if (contactsListElement && window.htmx) {
            htmx.ajax('GET', '/contatti', {
              target: contactsListElement,
              swap: 'outerHTML',
              select: '#contatti-list'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshContattiBadgeEvent');
          }
        }
        // --- Gestione DOCUMENTI (identica a LINK) ---
        if (payload.type === 'new_notification' && payload.data && payload.data.tipo === 'documento') {
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (!homeHighlightsElement) {
            console.warn('[WS][LOG] home-page-highlights NON TROVATO nel DOM (documento)');
          } else {
            console.log('[WS][LOG] home-page-highlights TROVATO nel DOM (documento), lancio HTMX');
          }
          fetch('/notifiche/inline')
            .then(response => response.text())
            .then(html => {
              if (html.includes(payload.data.id)) {
                Toastify({
                  text: payload.data.message,
                  duration: 4000,
                  gravity: 'top',
                  position: 'right',
                  backgroundColor: 'linear-gradient(to right, #00b09b, #96c93d)'
                }).showToast();
              }
            });
          if (homeHighlightsElement && window.htmx) {
            console.log('[WS] Aggiorno highlights (documento)');
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML',
              handler: function(xhr, target) {
                console.log('[WS] Risposta highlights (documento):', xhr && xhr.responseText ? xhr.responseText : '');
                return xhr && xhr.responseText ? xhr.responseText : '';
              }
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshDocumentiBadgeEvent');
          }
        }
        if (payload.type === 'remove_document' && payload.data) {
          let branch = payload.data.branch === '*' ? 'Tutti' : (payload.data.branch || '');
          let msg = 'Documento eliminato!';
          if (payload.data.title) {
            msg = `Documento eliminato: "${payload.data.title}" (${branch})`;
          }
          Toastify({
            text: msg,
            duration: 4000,
            gravity: 'top',
            position: 'right',
            backgroundColor: 'linear-gradient(to right, #ef4444, #f87171)'
          }).showToast();
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
          const documentsListElement = document.getElementById('documents-list');
          if (documentsListElement && window.htmx) {
            htmx.ajax('GET', '/documents', {
              target: documentsListElement,
              swap: 'outerHTML',
              select: '#documents-list'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshDocumentiBadgeEvent');
          }
        }
        if (payload.type === 'update_document' && payload.data) {
          let branch = payload.data.branch === '*' ? 'Tutti' : (payload.data.branch || '');
          let empType = payload.data.employment_type === '*' ? 'Tutte' : (payload.data.employment_type || '');
          let msg = 'Documento modificato!';
          if (payload.data.title) {
            msg = `Documento modificato: "${payload.data.title}" (${branch}, ${empType})`;
            if (payload.data.consequence) {
              msg += `\n${payload.data.consequence}`;
            }
          }
          Toastify({
            text: msg,
            duration: 4000,
            gravity: 'top',
            position: 'right',
            backgroundColor: 'linear-gradient(to right, #fbbf24, #f59e42)'
          }).showToast();
          // Aggiorna gli highlights come per i link
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
          // Emetti l'evento per HTMX
          htmx.trigger(document.body, 'update_document');
        }
        // --- Gestione NEWS (come LINK) ---
        if (payload.type === 'new_notification' && payload.data && payload.data.tipo === 'news') {
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (!homeHighlightsElement) {
            console.warn('[WS][LOG] home-page-highlights NON TROVATO nel DOM (news)');
          } else {
            console.log('[WS][LOG] home-page-highlights TROVATO nel DOM (news), lancio HTMX');
          }
          fetch('/notifiche/inline')
            .then(response => response.text())
            .then(html => {
              if (html.includes(payload.data.id)) {
                Toastify({
                  text: payload.data.message,
                  duration: 4000,
                  gravity: 'top',
                  position: 'right',
                  backgroundColor: 'linear-gradient(to right, #00b09b, #96c93d)'
                }).showToast();
              }
            });
          if (homeHighlightsElement && window.htmx) {
            console.log('[WS] Aggiorno highlights (news)');
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML',
              handler: function(xhr, target) {
                console.log('[WS] Risposta highlights (news):', xhr && xhr.responseText ? xhr.responseText : '');
                return xhr && xhr.responseText ? xhr.responseText : '';
              }
            });
          }
          // AGGIUNTA: aggiorna anche la barra news-ticker
          const newsTickerElement = document.getElementById('news-ticker');
          if (newsTickerElement && window.htmx) {
            htmx.ajax('GET', '/home/news_ticker/partial', {
              target: newsTickerElement,
              swap: 'outerHTML'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshNewsBadgeEvent');
          }
        }
        if (payload.type === 'remove_news' && payload.data) {
          let msg = 'News eliminata!';
          if (payload.data.title) {
            msg = `News eliminata: "${payload.data.title}" (${payload.data.branch || ''})`;
          }
          Toastify({
            text: msg,
            duration: 4000,
            gravity: 'top',
            position: 'right',
            backgroundColor: 'linear-gradient(to right, #ef4444, #f87171)'
          }).showToast();
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshNewsBadgeEvent');
          }
        }
        if (payload.type === 'update_news' && payload.data) {
          let msg = 'News modificata!';
          if (payload.data.title) {
            msg = `News modificata: "${payload.data.title}" (${payload.data.branch || ''})`;
            if (payload.data.consequence) {
              msg += `\n${payload.data.consequence}`;
            }
          }
          Toastify({
            text: msg,
            duration: 4000,
            gravity: 'top',
            position: 'right',
            backgroundColor: 'linear-gradient(to right, #fbbf24, #f59e42)'
          }).showToast();
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/home/highlights/partial', {
              target: homeHighlightsElement,
              swap: 'outerHTML'
            });
          }
          const newsRowElement = document.getElementById('news-' + payload.data.id);
          if (newsRowElement && window.htmx) {
            htmx.ajax('GET', `/news/${payload.data.id}/row_partial`, {
              target: newsRowElement,
              swap: 'outerHTML'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshNewsBadgeEvent');
          }
        }
        // --- Real time highlights per NEWS ---
        if (["update_news_highlight", "update_news", "remove_news"].includes(payload.type)) {
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (!homeHighlightsElement) {
            console.warn('[WS][LOG] home-page-highlights NON TROVATO nel DOM (news generico)');
          } else {
            console.log('[WS][LOG] home-page-highlights TROVATO nel DOM (news generico), lancio HTMX');
          }
          htmx.ajax('GET', '/home/highlights/partial', {
            target: homeHighlightsElement,
            swap: 'outerHTML',
            handler: function(xhr, target) {
              console.log('[WS] Risposta highlights (news generico):', xhr && xhr.responseText ? xhr.responseText : '');
              return xhr && xhr.responseText ? xhr.responseText : '';
            }
          });
        }
        // --- FINE LOGICA REAL-TIME UNIVERSALE ---
        // Aggiorna la barra news scorrevole e la lista news in real time
        if (["update_news_highlight", "update_news", "remove_news", "new_notification"].includes(payload.type) && (payload.data?.tipo === 'news' || payload.type.startsWith('update_news') || payload.type === 'remove_news')) {
          const newsTicker = document.getElementById('news-ticker');
          const newsList = document.getElementById('news-list');
          if (window.htmx) {
            if (newsTicker) {
              htmx.ajax('GET', '/home/news_ticker/partial', {
                target: newsTicker,
                swap: 'outerHTML'
              });
            }
            if (newsList) {
              htmx.ajax('GET', '/news/partial', {
                target: newsList,
                swap: 'innerHTML'
              });
            }
          }
        }
      } catch (e) {
        console.error('Errore parsing messaggio WebSocket: ' + e + ' | Dati: ' + event.data);
      }
    };
  }

  // Funzione globale per loggare come toast
  window.toastLog = function(msg) {
    console.log("[LOG]", msg);
  };

  // Funzione robusta per triggerare il badge dei contatti anche se non è subito nel DOM
  function triggerContattiBadgeEventRobusto() {
    const contattiBadge = document.getElementById('nav-contatti-badge-container');
    if (contattiBadge) {

      htmx.trigger(contattiBadge, 'refreshContattiBadgeEvent');
    } else {

      setTimeout(triggerContattiBadgeEventRobusto, 100);
    }
  }

  // Funzione robusta per aggiornare home-page-highlights
  function triggerHomeHighlightsRefresh(attempts = 0) {

    const homeHighlightsElement = document.getElementById('home-page-highlights');
    if (homeHighlightsElement && window.htmx) {
      htmx.ajax('GET', '/home/highlights/partial', {
        target: homeHighlightsElement,
        swap: 'outerHTML'
      });
    } else if (attempts < 10) { // Limite di retry per evitare loop infiniti
      setTimeout(() => triggerHomeHighlightsRefresh(attempts + 1), 100);
    } else {

    }
  }

  // Aggiorna lista news nella home in modo robusto (retry limitato)
  function triggerHomeNewsListRefresh(attempts = 0) {
    const homeNewsList = document.getElementById('home-news-list');
    if (homeNewsList && window.htmx) {
      htmx.ajax('GET', '/news/partial', {
        target: homeNewsList,
        swap: 'outerHTML'
      });
    } else if (attempts < 10) { // Limite di retry per evitare loop infiniti
      setTimeout(() => triggerHomeNewsListRefresh(attempts + 1), 100);
    }
  }
  triggerHomeNewsListRefresh();

  // Avvia la connessione WebSocket
  connectWebSocket();



  // Logga il contenuto HTML della partial highlights dopo ogni swap

  document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail && evt.detail.target && evt.detail.target.id === 'home-page-highlights') {
      const html = evt.detail.target.innerHTML || '';
      const preview = html.substring(0, 200) + (html.length > 200 ? '...' : '');
      console.log('[Highlights HTML dopo swap]', preview);
    }
  });

  // Stato globale per i commenti
  const commentsState = {};

  function initCommentsState(newsId) {
    commentsState[newsId] = {
        originalComments: [],
        filters: {
            text: '',
            sortBy: 'newest'
        }
    };
  }

  // Funzione per applicare filtri e ordinamento
  window.applyFiltersAndSort = function(newsId) {
    if (!commentsState[newsId]) {
        initCommentsState(newsId);
        return;
    }

    const sortSelect = document.getElementById(`sort-comments-${newsId}`);
    const sortBy = sortSelect ? sortSelect.value : 'newest';
    commentsState[newsId].filters.sortBy = sortBy;

    let filteredComments = [...commentsState[newsId].originalComments];

    // Applica ordinamento
    filteredComments.sort((a, b) => {
        switch (sortBy) {
            case 'oldest':
                return new Date(a.created_at) - new Date(b.created_at);
            case 'newest':
                return new Date(b.created_at) - new Date(a.created_at);
            case 'likes':
                return (b.likes || 0) - (a.likes || 0);
            case 'replies':
                return (b.replies?.length || 0) - (a.replies?.length || 0);
            default:
                return 0;
        }
    });

    // Renderizza i commenti filtrati e ordinati
    window.renderFlatChat(filteredComments, `comments-list-${newsId}`);
  };

  // Modifica loadCommentsForNews per usare lo stato e mantenere l'ordinamento
  function loadCommentsForNews() {
    const commentLists = document.querySelectorAll('[id^="comments-list-"]');
    commentLists.forEach(list => {
        const newsId = list.id.replace('comments-list-', '');
        if (!newsId || !window.htmx) return;
        if (!commentsState[newsId]) {
            initCommentsState(newsId);
        }
        fetch(`/api/ai-news/${newsId}/comments`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (!data || !data.items) {
                    throw new Error('Formato dati non valido');
                }
                commentsState[newsId].originalComments = data.items;
                applyFiltersAndSort(newsId);
            })
            .catch(error => {
                console.error('Errore caricamento commenti:', error);
                const errorDiv = document.createElement('div');
                errorDiv.className = 'text-red-500 text-sm mt-2';
                errorDiv.textContent = 'Errore nel caricamento dei commenti. Riprova più tardi.';
                list.appendChild(errorDiv);
            });
    });
  }
  loadCommentsForNews();

  window.toggleComments = function(newsId) {
    const commentsSection = document.querySelector(`#comments-section-${newsId}`);
    if (commentsSection) {
        commentsSection.classList.toggle('hidden');
    }
  };

  window.updateCommentsCount = async function(newsId) {
    try {
        const response = await fetch(`/api/ai-news/${newsId}/stats`);
        if (!response.ok) throw new Error('Errore nel recupero conteggio commenti');
        const data = await response.json();
        const countSpan = document.querySelector(`#comments-${newsId} .stats-count`);
        if (countSpan) {
            countSpan.textContent = data.stats.comments || 0;
        }
    } catch (error) {
        console.error('Errore nell\'aggiornamento del conteggio commenti:', error);
    }
  };

  // Funzione globale per il filtraggio dei commenti
  window.filterComments = function(newsId) {
    const searchInput = document.querySelector(`#search-comments-${newsId}`);
    if (!commentsState[newsId]) {
        initCommentsState(newsId);
    }
    commentsState[newsId].filters.text = searchInput.value.toLowerCase();
    applyFiltersAndSort(newsId);
  };

  // Traccia la visualizzazione una sola volta per sessione per ogni documento
  const viewedDocs = new Set();

  window.toggleViews = async function(newsId) {
    // Se il documento è già stato visualizzato in questa sessione, non contare una nuova visualizzazione
    if (viewedDocs.has(newsId)) return;
    try {
        const response = await fetch(`/api/ai-news/${newsId}/view`, {
            method: 'POST',
            credentials: 'include'
        });
        if (!response.ok) throw new Error('Errore nel conteggio visualizzazione');
        const data = await response.json();
        const viewCount = document.querySelector(`#views-${newsId} .stats-count`);
        if (viewCount && typeof data.stats !== 'undefined') {
            viewCount.textContent = data.stats.views;
        }
        // Aggiungi il documento al set dei documenti visualizzati
        viewedDocs.add(newsId);
    } catch (error) {

    }
  };

  // Traccia automaticamente la visualizzazione quando si apre l'anteprima
  document.addEventListener('click', function(e) {
    const previewLink = e.target.closest('a[href^="/ai-news/"][href$="/preview"]');
    if (previewLink) {
        const newsId = previewLink.getAttribute('href').split('/')[2];
        toggleViews(newsId);
    }
  });
  // Traccia automaticamente la visualizzazione quando si scarica la news
  document.addEventListener('click', function(e) {
    const downloadLink = e.target.closest('a[href^="/ai-news/"]');
    if (downloadLink && !downloadLink.getAttribute('href').endsWith('/preview')) {
        const newsId = downloadLink.getAttribute('href').split('/')[2];
        toggleViews(newsId);
    }
  });

  // Dopo l'invio del form di risposta, nascondi il form
  document.body.addEventListener('htmx:afterOnLoad', function(evt) {
    if (evt.detail.elt && evt.detail.elt.tagName === 'FORM' && evt.detail.elt.closest('[id^="reply-form-"]')) {
      const replyForm = evt.detail.elt.closest('[id^="reply-form-"]');
      const commentId = replyForm.id.replace('reply-form-', '');
      hideReplyForm(commentId);
    }
  });

  document.querySelectorAll('.delete-comment-btn').forEach(btn => {
    const authorId = btn.getAttribute('data-author-id');
    const commentId = btn.getAttribute('data-comment-id');
    if (window.currentUserRole === 'admin' || window.currentUserId === authorId) {
      btn.classList.remove('hidden');
    } else {
      btn.classList.add('hidden');
    }
  });

  // Funzione per renderizzare la chat piatta
  window.renderFlatChat = function(messages, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    // Ricavo newsId dal containerId se serve
    const newsId = (messages[0]?.ai_news_id || messages[0]?.news_id || containerId.replace('comments-list-', ''));
    container.innerHTML = '';
    messages.forEach(msg => {
      const isCurrentUserComment = msg.author_id === window.currentUserId;
      const msgDiv = document.createElement('div');
      msgDiv.className = `chat-message flex items-start gap-3 mb-4 ${isCurrentUserComment ? 'bg-emerald-100' : 'bg-blue-50'}`;
      msgDiv.id = `msg-${msg._id}`;
      msgDiv.innerHTML = `
        <img src="${msg.author?.avatar || '/static/img/avatar-default.png'}" class="comment-avatar">
        <div class="bubble flex-1">
          <div class="flex items-center gap-2 mb-1">
            <span class="comment-author">${msg.author?.name || 'Utente'}</span>
            <span class="text-xs text-gray-500">${msg.created_at ? new Date(msg.created_at).toLocaleString('it-IT') : ''}</span>
          </div>
          ${msg.reply_to_name ? `
            <div class="text-xs text-blue-600 mb-1 flex items-center gap-1">
              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
              </svg>
              <span>in risposta a: ${msg.reply_to_name}</span>
            </div>
          ` : ''}
          <div class="comment-content">${window.marked ? marked.parse(msg.content) : msg.content}</div>
          <div class="comment-actions mt-2 flex gap-2">
            <button onclick="showReplyForm('${msg._id}', '${msg.ai_news_id || msg.news_id || newsId}')" class="flex items-center space-x-1 text-gray-500 hover:text-blue-600 text-sm">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
              </svg>
              <span>Rispondi</span>
            </button>
            ${(window.currentUserRole === 'admin' || window.currentUserId === msg.author_id) ? `
            <button onclick="deleteComment('${msg._id}')" class="flex items-center space-x-1 text-gray-500 hover:text-red-600 text-sm">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
              </svg>
              <span>Elimina</span>
            </button>` : ''}
          </div>
        </div>
      `;
      container.appendChild(msgDiv);
      // AGGIUNGO IL CONTAINER PER IL FORM DI RISPOSTA SOTTO OGNI COMMENTO
      const replyContainer = document.createElement('div');
      replyContainer.id = `reply-form-container-${msg._id}`;
      container.appendChild(replyContainer);
    });
  };

  // Permetti invio con Enter anche per i form di nuovo commento
  // (solo se il form ha un solo textarea e un solo submit)
  document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded event fired');
    document.querySelectorAll('form').forEach(form => {
      // Cerca textarea e bottone submit
      const textarea = form.querySelector('textarea[name="content"]');
      const submitBtn = form.querySelector('button[type="submit"]');
      if (textarea && submitBtn) {
        textarea.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' && !e.shiftKey) {
            // Solo se non c'è un attributo data-disable-enter-submit (per opt-out)
            if (!textarea.hasAttribute('data-disable-enter-submit')) {
              // Verifica se il menu delle menzioni è attivo
              const mentionsMenu = textarea.parentNode.querySelector('.mentions-menu');
              if (!mentionsMenu || mentionsMenu.children.length === 0) {
                e.preventDefault();
                // Simula submit solo se il bottone non è disabilitato
                if (!submitBtn.disabled) {
                  form.dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
                }
              }
            }
          }
        });
      }
    });
  });

  // ===================== MENZIONI CHAT =====================
  class MentionsHandler {
    constructor(textarea) {
      console.log('MentionsHandler inizializzato per:', textarea);
      this.textarea = textarea;
      this.menuContainer = null;
      this.users = [];
      this.mentionStart = -1;
      this.currentQuery = '';
      this.textarea.addEventListener('keyup', this.handleKeyUp.bind(this));
      this.textarea.addEventListener('keydown', this.handleKeyDown.bind(this));
    }
    async fetchUsers() {
      console.log('Fetching users...');
      try {
        const response = await fetch('/api/users/mentions');
        if (!response.ok) throw new Error('Errore nel caricamento degli utenti');
        this.users = await response.json();
        console.log('Users fetched:', this.users);
      } catch (error) {
        console.error('Errore nel caricamento degli utenti:', error);
      }
    }
    createMenu() {
      this.menuContainer = document.createElement('div');
      this.menuContainer.className = 'mentions-menu';
      this.textarea.parentNode.appendChild(this.menuContainer);
    }
    handleKeyUp(e) {
      const text = this.textarea.value;
      const pos = this.textarea.selectionStart;
      console.log('KeyUp - Char:', text[pos - 1], 'Position:', pos);
      // Controlla se il carattere '@' è stato eliminato o non è più presente
      if (this.mentionStart >= 0) {
        const currentText = text.substring(this.mentionStart, pos);
        if (!currentText.startsWith('@')) {
          this.hideMenu();
          return;
        }
      }
      if (text[pos - 1] === '@' && this.mentionStart === -1) {
        console.log('@ detected, starting mentions...');
        this.mentionStart = pos - 1;
        this.currentQuery = '';
        this.fetchUsers();
        this.showMenu();
      } else if (this.mentionStart >= 0) {
        this.currentQuery = text.substring(this.mentionStart + 1, pos);
        console.log('Current query:', this.currentQuery);
        this.updateMenu();
      }
    }
    handleKeyDown(e) {
      if (this.menuContainer && this.menuContainer.children.length > 0) {
        if (e.key === 'Enter' && this.menuContainer.querySelector('.selected')) {
          e.preventDefault();
          this.selectCurrentUser();
        } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          this.navigateMenu(e.key === 'ArrowDown');
        } else if (e.key === 'Escape') {
          this.hideMenu();
        }
      }
    }
    showMenu() {
      if (!this.menuContainer) this.createMenu();
      this.updateMenu();
    }
    updateMenu() {
      if (!this.menuContainer) return;
      const filteredUsers = this.users.filter(user =>
        user.name.toLowerCase().includes(this.currentQuery.toLowerCase()) ||
        user.email.toLowerCase().includes(this.currentQuery.toLowerCase())
      );
      this.menuContainer.innerHTML = filteredUsers
        .map((user, i) => `
          <div class="mentions-menu-item ${i === 0 ? 'selected' : ''}" 
               data-user-id="${user.id}" 
               data-user-name="${user.name}">
              ${user.name} (${user.email})
          </div>
        `)
        .join('');
      this.menuContainer.querySelectorAll('.mentions-menu-item').forEach(item => {
        item.addEventListener('click', () => this.selectUser(item));
      });
    }
    navigateMenu(down) {
      const items = this.menuContainer.querySelectorAll('.mentions-menu-item');
      const current = this.menuContainer.querySelector('.selected');
      let next;
      if (down) {
        next = current.nextElementSibling || items[0];
      } else {
        next = current.previousElementSibling || items[items.length - 1];
      }
      current.classList.remove('selected');
      next.classList.add('selected');
    }
    selectUser(item) {
      const userId = item.dataset.userId;
      const userName = item.dataset.userName;
      const text = this.textarea.value;
      const newText = 
        text.substring(0, this.mentionStart) +
        `@[${userName}](${userId})` +
        text.substring(this.textarea.selectionStart);
      this.textarea.value = newText;
      this.hideMenu();
    }
    selectCurrentUser() {
      const selected = this.menuContainer.querySelector('.selected');
      if (selected) this.selectUser(selected);
    }
    hideMenu() {
      if (this.menuContainer) {
        this.menuContainer.remove();
        this.menuContainer = null;
      }
      this.mentionStart = -1;
      this.currentQuery = '';
    }
  }
  // =================== FINE MENZIONI CHAT ===================

  // ========== MENZIONI: INIZIALIZZAZIONE UNIVERSALE ==========
  (function() {
    function initMentionsOnTextareas() {
      document.querySelectorAll('textarea[name="content"]:not([data-mentions-initialized])').forEach(textarea => {
        new MentionsHandler(textarea);
        textarea.setAttribute('data-mentions-initialized', 'true');
      });
    }
    // Inizializza su DOM pronto
    document.addEventListener('DOMContentLoaded', initMentionsOnTextareas);
    // Inizializza su mutazioni DOM (es. HTMX, JS)
    const observer = new MutationObserver(() => {
      initMentionsOnTextareas();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  })();

  // Inizializza MentionsHandler per tutti i form di commento (statici)
  document.querySelectorAll('form[hx-post*="/api/ai-news/"][hx-post$="/comments"]').forEach(form => {
    const textarea = form.querySelector('textarea[name="content"]');
    if (textarea) {
      console.log('Initializing MentionsHandler for textarea:', textarea);
      new MentionsHandler(textarea);
    }
  });

  // Inizializza anche per i form caricati dinamicamente tramite HTMX
  document.body.addEventListener('htmx:afterSwap', function(event) {
    console.log('htmx:afterSwap event fired');
    const newForms = event.detail.target.querySelectorAll('form[hx-post*="/api/ai-news/"][hx-post$="/comments"]');
    console.log('Found new forms after swap:', newForms.length);
    newForms.forEach(form => {
      const textarea = form.querySelector('textarea[name="content"]');
      if (textarea) {
        console.log('Initializing MentionsHandler for new textarea:', textarea);
        new MentionsHandler(textarea);
      }
    });
  });

  // Gestione reset form dopo invio commento
  // Dopo DOMContentLoaded

  document.body.addEventListener('htmx:afterSwap', function(evt) {
    // Verifica se il target è un container di commenti
    if (evt.detail.target && evt.detail.target.id && evt.detail.target.id.startsWith('comments-list-')) {
      // Trova il form più vicino al target
      const form = evt.detail.target.closest('.comments-container').querySelector('form');
      if (form) {
        // Resetta il form
        form.reset();
        // Resetta anche il contatore caratteri
        const newsId = evt.detail.target.id.split('-').pop();
        const charCount = document.querySelector(`#char-count-${newsId}`);
        if (charCount) {
          charCount.textContent = '1000';
        }
        // Nascondi l'anteprima se visibile
        const preview = form.querySelector('[id^="preview-"]');
        if (preview && !preview.classList.contains('hidden')) {
          preview.classList.add('hidden');
          const previewButton = form.querySelector('button[onclick^="togglePreview"]');
          if (previewButton) {
            previewButton.querySelector('span').textContent = 'Anteprima Markdown';
          }
        }
      }
    }
  });

  // Emoji picker
  const commonEmojis = [
    '😀', '🤣', '😊', '😍', '🥰', '😎', '🤔', '😅', '😇',
    '👍', '👎', '👏', '🙌', '👋', '❤️', '🎉', '✨', '🔥'
  ];

  window.toggleEmojiPicker = function(button) {
    const existingPicker = document.querySelector('.emoji-picker');
    if (existingPicker) {
        existingPicker.remove();
        return;
    }

    const picker = document.createElement('div');
    picker.className = 'emoji-picker absolute bg-white border border-gray-200 rounded-lg shadow-lg p-2 grid grid-cols-5 gap-1';
    picker.style.zIndex = '9999';
    
    // Aggiungi gli emoji al picker
    commonEmojis.forEach(emoji => {
        const emojiButton = document.createElement('button');
        emojiButton.type = 'button';
        emojiButton.className = 'w-8 h-8 hover:bg-gray-100 rounded flex items-center justify-center text-xl';
        emojiButton.textContent = emoji;
        emojiButton.onclick = (e) => {
            e.stopPropagation();
            insertEmoji(emoji, button);
            picker.remove();
        };
        picker.appendChild(emojiButton);
    });

    // Aggiungi il picker vicino al bottone invece che al body
    button.parentElement.appendChild(picker);

    // Calcola la posizione relativa al contenitore del bottone
    const buttonRect = button.getBoundingClientRect();
    const pickerRect = picker.getBoundingClientRect();
    const containerRect = button.parentElement.getBoundingClientRect();

    // Posiziona il picker sopra il bottone per default
    let top = -pickerRect.height - 5;
    let left = buttonRect.left - containerRect.left;

    // Se non c'è spazio sopra, posiziona sotto
    if (buttonRect.top < pickerRect.height) {
        top = buttonRect.height + 5;
    }

    // Assicurati che il picker non vada fuori dallo schermo orizzontalmente
    if (left + pickerRect.width > window.innerWidth) {
        left = window.innerWidth - pickerRect.width - containerRect.left - 5;
    }
    if (left < 0) {
        left = 5;
    }

    picker.style.top = `${top}px`;
    picker.style.left = `${left}px`;

    // Gestisci la chiusura quando si clicca fuori
    const closePickerOnClick = (e) => {
        if (!picker.contains(e.target) && e.target !== button) {
            picker.remove();
            document.removeEventListener('click', closePickerOnClick);
        }
    };
    
    setTimeout(() => {
        document.addEventListener('click', closePickerOnClick);
    }, 100);
  };

  function insertEmoji(emoji, button) {
    const textarea = button.parentElement.querySelector('textarea');
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    
    textarea.value = text.substring(0, start) + emoji + text.substring(end);
    textarea.focus();
    textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
    
    // Trigger l'evento input per aggiornare il contatore dei caratteri
    textarea.dispatchEvent(new Event('input'));
  }

  window.insertEmoji = insertEmoji;

  // ===================== RISPOSTE AI COMMENTI =====================
  // ⚠️ AVVISO DI MORTE ⚠️
  // CHIUNQUE TOCCHI QUESTA SEZIONE SENZA AUTORIZZAZIONE SARÀ MALEDETTO DA 1000 BUG
  // NON MODIFICARE QUESTA LOGICA SENZA APPROVAZIONE DEL RESPONSABILE
  // (Lasciare intatta la logica di risposta ai commenti, pena la rottura della chat e la furia degli utenti)
  // RIPETIAMO: NON TOCCARE QUESTA SEZIONE!

  window.showReplyForm = function(commentId, newsId) {
      console.log('[DEBUG] showReplyForm chiamata con:', commentId, newsId);

      // Nascondi altri form
      document.querySelectorAll('[id^="reply-form-"]').forEach(form => {
          if (form.id !== `reply-form-${commentId}`) {
              form.classList.add('hidden');
          }
      });

      let replyForm = document.getElementById(`reply-form-${commentId}`);
      console.log('[DEBUG] replyForm trovato:', replyForm);

      if (!replyForm) {
          const container = document.getElementById(`reply-form-container-${commentId}`);
          console.log('[DEBUG] container trovato:', container);

          if (container) {
              replyForm = document.createElement('div');
              replyForm.id = `reply-form-${commentId}`;
              replyForm.innerHTML = `
                  <form id="comment-form-${commentId}" class="mt-4 space-y-4" onsubmit="event.preventDefault(); addComment('${newsId}', '${commentId}')">
                      <div class="relative">
                          <textarea 
                              name="content" 
                              rows="3" 
                              maxlength="500"
                              class="block w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                              placeholder="Scrivi una risposta..."
                              onkeyup="updateCharCount(this, '${commentId}')"
                              onkeydown="if(event.key === 'Enter' && !event.shiftKey && !this.hasAttribute('data-disable-enter-submit')) { 
                                  const mentionsMenu = this.parentNode.querySelector('.mentions-menu');
                                  if (!mentionsMenu || mentionsMenu.children.length === 0) {
                                      event.preventDefault(); 
                                      this.closest('form').dispatchEvent(new Event('submit')); 
                                  }
                              }"
                          ></textarea>
                          <div class="absolute bottom-2 right-2 text-xs text-gray-500">
                              <span id="char-count-${commentId}">500</span> caratteri rimanenti
                          </div>
                      </div>
                      <div class="flex justify-end space-x-2">
                          <button type="button" onclick="hideReplyForm('${commentId}')" class="px-4 py-2 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200">Annulla</button>
                          <button type="submit" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700" disabled>
                              <span class="loading-spinner hidden">⏳</span>
                              <span>Invia Risposta</span>
                          </button>
                      </div>
                  </form>
              `;
              container.appendChild(replyForm);
              console.log('[DEBUG] replyForm creato e aggiunto:', replyForm);
              console.log('[DEBUG] container.innerHTML dopo append:', container.innerHTML);
          } else {
              console.warn('[DEBUG] container NON trovato per', commentId);
          }
      }

      if (replyForm) {
          replyForm.classList.remove('hidden');
          const textarea = replyForm.querySelector('textarea');
          if (textarea) {
              // Aggiungi l'evento keydown per il tasto Enter
              textarea.addEventListener('keydown', function(e) {
                  if (e.key === 'Enter' && !e.shiftKey) {
                      // Solo se non c'è un attributo data-disable-enter-submit
                      if (!textarea.hasAttribute('data-disable-enter-submit')) {
                          // Verifica se il menu delle menzioni è attivo
                          const mentionsMenu = textarea.parentNode.querySelector('.mentions-menu');
                          if (!mentionsMenu || mentionsMenu.children.length === 0) {
                              e.preventDefault();
                              // Simula il click sul pulsante di invio
                              const submitBtn = replyForm.querySelector('button[type="submit"]');
                              if (submitBtn && !submitBtn.disabled) {
                                  replyForm.dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
                              }
                          }
                      }
                  }
              });
              textarea.focus();
              console.log('[DEBUG] textarea trovata e focus:', textarea);
          } else {
              console.warn('[DEBUG] textarea NON trovata nel replyForm');
          }
      } else {
          console.warn('[DEBUG] replyForm NON trovato/creato');
      }
  };

  window.hideReplyForm = function(commentId) {
      // Trova sia il container che il form
      const replyFormContainer = document.getElementById(`reply-form-container-${commentId}`);
      const replyForm = document.getElementById(`reply-form-${commentId}`);
      // Nascondi il form se esiste
      if (replyForm) {
          replyForm.classList.add('hidden');
          // Reset del form
          const textarea = replyForm.querySelector('textarea');
          if (textarea) {
              textarea.value = '';
              updateCharCount(textarea, commentId);
          }
      }
      // Opzionalmente, pulisci il container
      if (replyFormContainer) {
          replyFormContainer.innerHTML = '';
      }
  };

  window.addComment = async function(newsId, parentId = null) {
    const form = document.querySelector(`#${parentId ? `reply-form-${parentId}` : `comment-form-${newsId}`}`);
    if (!form) return;
    const textarea = form.querySelector('textarea');
    if (!textarea) return;
    const content = textarea.value.trim();
    if (!content) return;
    try {
      const formData = new FormData();
      formData.append('content', content);
      if (parentId) {
        formData.append('parent_id', parentId);
      }
      const response = await fetch(`/api/ai-news/${newsId}/comments`, {
        method: 'POST',
        body: formData
      });
      if (!response.ok) throw new Error('Network response was not ok');
      const data = await response.json();
      textarea.value = '';
      if (parentId) {
        hideReplyForm(parentId);
      }
      // Aggiorna immediatamente la lista dei commenti
      const commentsList = document.getElementById(`comments-list-${newsId}`);
      if (commentsList) {
        fetch(`/api/ai-news/${newsId}/comments`)
          .then(response => response.json())
          .then(data => {
            window.renderFlatChat(data.items, `comments-list-${newsId}`);
            updateCommentsCount(newsId);
          });
      }
      return data;
    } catch (error) {
      console.error('Error adding comment:', error);
      if (typeof Toastify !== 'undefined') {
        Toastify({
          text: 'Errore durante l\'invio del commento',
          duration: 3000,
          gravity: 'top',
          position: 'right',
          backgroundColor: '#ef4444'
        }).showToast();
      }
      throw error;
    }
  };

  // Funzione per aggiornare solo il contatore caratteri
  window.updatePreview = function(textarea, newsId) {
    updateCharCount(textarea, newsId);
  };

  // Funzione per mostrare/nascondere l'anteprima Markdown
  window.togglePreview = function(newsId) {
    const preview = document.getElementById(`preview-${newsId}`);
    const textarea = document.getElementById(`comment-input-${newsId}`);
    if (preview && textarea) {
      if (preview.classList.contains('hidden')) {
        // Mostra anteprima
        const content = textarea.value.trim();
        if (content && window.marked) {
          preview.innerHTML = marked.parse(content);
          preview.classList.remove('hidden');
        }
      } else {
        // Nascondi anteprima
        preview.classList.add('hidden');
      }
    }
  };

  // Funzione per gestire i like delle news
  window.likeNews = async function(newsId) {
    try {
      const response = await fetch(`/api/ai-news/${newsId}/like`, {
        method: 'POST',
        credentials: 'include'
      });
      // Verifica se la risposta è JSON
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        // Se non è JSON, probabilmente siamo stati reindirizzati al login
        window.location.href = '/login';
        return;
      }
      if (!response.ok) throw new Error('Errore nel like della news');
      const data = await response.json();
      const likeBtn = document.querySelector(`#likes-${newsId} .like-button`);
      const likeCount = likeBtn?.querySelector('.stats-count');
      if (likeBtn && likeCount && typeof data.stats !== 'undefined') {
        likeBtn.dataset.liked = data.user_has_liked.toString();
        likeBtn.querySelector('svg').setAttribute('fill',
          data.user_has_liked ? 'currentColor' : 'none'
        );
        likeCount.textContent = data.stats.likes;
      }
    } catch (error) {
      console.error('Errore:', error);
      // Mostra un messaggio di errore all'utente
      if (typeof Toastify !== 'undefined') {
        Toastify({
          text: 'Si è verificato un errore. Riprova più tardi.',
          duration: 3000,
          gravity: 'top',
          position: 'right',
          backgroundColor: '#ef4444'
        }).showToast();
      }
    }
  };

  window.deleteComment = async function(commentId) {
    try {
        const response = await fetch(`/api/ai-news/comments/${commentId}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        if (!response.ok) throw new Error('Errore nell\'eliminazione del commento');
        // Il commento verrà rimosso automaticamente dal DOM grazie al WebSocket broadcast
    } catch (error) {
        console.error('Errore:', error);
        if (typeof Toastify !== 'undefined') {
            Toastify({
                text: 'Errore durante l\'eliminazione del commento',
                duration: 3000,
                gravity: 'top',
                position: 'right',
                backgroundColor: '#ef4444'
            }).showToast();
        }
    }
  };

  // Funzione per condividere una news
  window.shareNews = function(newsId, title) {
    const url = `${window.location.origin}/ai-news/${newsId}/download`;
    // Usa l'API Web Share se disponibile
    if (navigator.share) {
      navigator.share({
        title: title,
        url: url
      }).catch(err => {
        console.error('Errore durante la condivisione:', err);
        copyToClipboard(url);
      });
    } else {
      // Fallback: copia il link negli appunti
      copyToClipboard(url);
    }
  };
  // Funzione di supporto per copiare negli appunti
  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
      if (typeof Toastify !== 'undefined') {
        Toastify({
          text: 'Link copiato negli appunti!',
          duration: 3000,
          gravity: 'top',
          position: 'right',
          backgroundColor: 'linear-gradient(to right, #00b09b, #96c93d)'
        }).showToast();
      }
    }).catch(err => {
      console.error('Errore durante la copia negli appunti:', err);
    });
  }

  // Gestione WebSocket per aggiornamento real-time News AI
  if (window.ws) {
    window.ws.addEventListener('message', function(event) {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (payload.type === 'update_ai_news' && payload.data) {
        const newsId = payload.data.id;
        if (window.location.pathname === '/ai-news') {
          window.location.reload();
        }
      }
      if (payload.type === 'remove_ai_news' && payload.data) {
        const newsId = payload.data.id;
        const newsElement = document.getElementById(`ai-news-${newsId}`);
        if (newsElement) {
          newsElement.remove();
        }
      }
    });
  }

  document.body.addEventListener('refreshContattiList', function() {
    const contactsListElement = document.getElementById('contatti-list');
    if (contactsListElement && window.htmx) {
      htmx.ajax('GET', '/contatti', {
        target: contactsListElement,
        swap: 'innerHTML'
      });
    }
  });

  document.body.addEventListener('htmx:swapError', function(evt) {
    // Mostra il toast SOLO se il target dell'errore è la lista documenti
    if (
      evt.detail &&
      evt.detail.target &&
      evt.detail.target.id === 'documents-list'
    ) {
      if (window.htmx) {
        htmx.ajax('GET', '/documents', {
          target: evt.detail.target,
          swap: 'outerHTML',
          select: '#documents-list'
        });
      }
      if (typeof Toastify !== "undefined") {
        Toastify({
          text: "Documento aggiornato. La lista è stata aggiornata.",
          duration: 4000,
          gravity: 'top',
          position: 'right',
          backgroundColor: 'linear-gradient(to right, #fbbf24, #f59e42)'
        }).showToast();
      }
    }
    // Chiudi la modale sempre
    window.closeModal && window.closeModal();

    // Aggiorna il badge dei documenti
    if (window.htmx) {
      setTimeout(() => {
        htmx.trigger(document.body, 'refreshDocumentiBadgeEvent');
      }, 100);
    }
  });

  // Nascondi la barra news prima dello swap per evitare flicker/layout errato
  htmx.on('htmx:beforeSwap', function(evt) {
    if (evt.detail && evt.detail.target && evt.detail.target.id === 'news-ticker') {
      evt.detail.target.style.visibility = 'hidden';
    }
  });
  // Dopo lo swap, mostra la barra e forza il reflow
  htmx.on('htmx:afterSwap', function(evt) {
    if (evt.detail && evt.detail.target && evt.detail.target.id === 'news-ticker') {
      // Forza il reflow per correggere eventuali problemi di layout
      evt.detail.target.style.display = 'none';
      void evt.detail.target.offsetWidth;
      evt.detail.target.style.display = '';
      evt.detail.target.style.visibility = '';
    }
  });

  document.body.addEventListener('closeModal', function() {
    // Aggiorna la barra delle news
    const newsTicker = document.getElementById('news-ticker');
    if (newsTicker && window.htmx) {
      htmx.ajax('GET', '/home/news_ticker/partial', {
        target: newsTicker,
        swap: 'outerHTML'
      });
    }
    // Aggiorna la lista delle news (se presente)
    const newsList = document.getElementById('news-list');
    if (newsList && window.htmx) {
      htmx.ajax('GET', '/news/partial', {
        target: newsList,
        swap: 'innerHTML'
      });
    }
  });

  // --- Scroll automatico news-ticker continuo (unica versione) ---
  let newsTickerScrollInterval = null;

  function startContinuousNewsTickerScroll() {
    // Ferma eventuali intervalli precedenti
    if (newsTickerScrollInterval) {
      clearInterval(newsTickerScrollInterval);
      newsTickerScrollInterval = null;
    }
    const ticker = document.querySelector('#news-ticker .overflow-x-auto');
    if (!ticker) {
      console.log('[NewsTicker] Contenitore non trovato');
      return;
    }
    console.log('[NewsTicker] Scroll automatico avviato');
    newsTickerScrollInterval = setInterval(() => {
      ticker.scrollLeft += 2;
      if (ticker.scrollLeft + ticker.clientWidth >= ticker.scrollWidth - 2) {
        ticker.scrollLeft = 0;
      }
    }, 16);
  }

  document.addEventListener('DOMContentLoaded', startContinuousNewsTickerScroll);
  document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail && evt.detail.target && evt.detail.target.id === 'news-ticker') {
      startContinuousNewsTickerScroll();
    }
  });
});