// Test diretto Toastify all'avvio
// if (typeof Toastify === "undefined") {
//   alert("Toastify NON è caricato all'avvio!");
//   console.error("Toastify NON è caricato all'avvio!");
// } else {
//   alert("Toastify è caricato correttamente!");
// }

// Tutto il codice che accede al DOM dentro DOMContentLoaded

document.addEventListener('DOMContentLoaded', () => {
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
  window.ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/notify');
  ws.onopen = function() {};
  ws.onerror = function(e) { console.error('WebSocket errore: ' + e.message); };
  ws.onclose = function() {};

  let shownToastIds = JSON.parse(sessionStorage.getItem('shownToastIds') || '[]');

  function displayToast(notification) {
    if (typeof Toastify === "undefined") {
      alert('Toastify non è caricato!');
      console.error('Toastify non è caricato!');
      return;
    }
    if (!shownToastIds.includes(notification.id)) {
      Toastify({
        text: notification.message,
        duration: 4000,
        gravity: 'top',
        position: 'right',
        backgroundColor: '#fbbf24'
      }).showToast();
      shownToastIds.push(notification.id);
      sessionStorage.setItem('shownToastIds', JSON.stringify(shownToastIds.slice(-20)));
    }
  }

  ws.addEventListener('message', function(event) {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === 'new_notification' && payload.data) {
        displayToast(payload.data);
        if (payload.data.message && payload.data.message.includes('link')) {
          const homeHighlightsElement = document.getElementById('home-page-highlights');
          if (homeHighlightsElement && window.htmx) {
            htmx.ajax('GET', '/', {
              target: homeHighlightsElement,
              swap: 'outerHTML',
              select: '#home-page-highlights'
            });
          }
          if (window.htmx) {
            htmx.trigger(document.body, 'refreshLinkBadgeEvent');
          }
        }
      } else if (payload.type === 'remove_link' && payload.data) {
        const homeHighlightsElement = document.getElementById('home-page-highlights');
        if (homeHighlightsElement && window.htmx) {
          htmx.ajax('GET', '/', {
            target: homeHighlightsElement,
            swap: 'outerHTML',
            select: '#home-page-highlights'
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
      } else if (payload.type === 'update_link' && payload.data) {
        const homeHighlightsElement = document.getElementById('home-page-highlights');
        if (homeHighlightsElement && window.htmx) {
          htmx.ajax('GET', '/', {
            target: homeHighlightsElement,
            swap: 'outerHTML',
            select: '#home-page-highlights'
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
    } catch (e) {
      console.error('Errore parsing messaggio WebSocket: ' + e + ' | Dati: ' + event.data);
    }
  });

  // (Struttura base per badge, da completare nei prossimi step)
  // function updateBadge(count) {
  //   const badge = document.getElementById('nav-links-badge-container');
  //   if (badge) {
  //     badge.textContent = count > 0 ? count : '';
  //   }
  // }
}); 