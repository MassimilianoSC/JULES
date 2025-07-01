import { eventBus } from '/static/js/core/event-bus.js';
import { showToast } from '/static/js/features/notifications/toast.js';

// Rimuovi tutti i Service Worker registrati
if ('serviceWorker' in navigator) {
    console.log('[CLEANUP] Inizio pulizia Service Workers...');
    
    // Prima disabilita eventuali Service Worker attivi
    if (navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage('SKIP_WAITING');
    }
    
    // Poi rimuovi tutte le registrazioni
    navigator.serviceWorker.getRegistrations()
        .then(registrations => {
            if (registrations.length === 0) {
                console.log('[CLEANUP] Nessun Service Worker trovato');
                return;
            }
            
            return Promise.all(
                registrations.map(registration => {
                    console.log('[CLEANUP] Rimozione Service Worker:', registration.scope);
                    return registration.unregister()
                        .then(success => {
                            if (success) {
                                console.log('[CLEANUP] Service Worker rimosso con successo:', registration.scope);
                            } else {
                                console.warn('[CLEANUP] Impossibile rimuovere Service Worker:', registration.scope);
                            }
                        });
                })
            );
        })
        .then(() => {
            console.log('[CLEANUP] Pulizia Service Workers completata');
            // Ricarica la pagina solo se c'erano Service Worker attivi
            if (navigator.serviceWorker.controller) {
                console.log('[CLEANUP] Ricarico la pagina per applicare le modifiche...');
                window.location.reload();
            }
        })
        .catch(error => {
            console.error('[CLEANUP] Errore durante la pulizia:', error);
        });
}

// Gestione eliminazione risorse
document.addEventListener('click', e => {
  const deleteLink = e.target.closest('[data-delete-url]');
  
  if (deleteLink) {
    e.preventDefault();
    
    Swal.fire({
      title: 'Sei sicuro?',
      text: 'Questa azione non può essere annullata',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Sì, elimina',
      cancelButtonText: 'Annulla',
      reverseButtons: true
    }).then((result) => {
      if (result.isConfirmed) {
        // Esegui l'eliminazione HTMX
        htmx.trigger(deleteLink, 'click');
        
        // Emetti evento di eliminazione
        const url = deleteLink.getAttribute('href');
        const type = url.split('/')[1]; // Estrai il tipo dalla URL (documents, ai-news, etc)
        const id = url.split('/')[2];   // Estrai l'ID dalla URL
        
        eventBus.emit('resource/delete', { type, id });
        
        // Mostra toast di conferma
        showToast({
          title: 'Eliminazione completata',
          body: 'La risorsa è stata eliminata con successo',
          type: 'success'
        });
      }
    });
  }
}); 