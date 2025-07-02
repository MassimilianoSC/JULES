// static/js/features/contact-delete.js
import { eventBus } from '/static/js/core/event-bus.js';

/**
 * Inizializza i gestori per i pulsanti di eliminazione dei contatti.
 * Utilizza HTMX per la richiesta DELETE dopo conferma tramite SweetAlert.
 */
export function initContactDeleteHandlers() {
  document.addEventListener('click', async (e) => {
    const deleteBtn = e.target.closest('.btn-delete-contact'); // Selettore specifico per i bottoni elimina contatto
    if (!deleteBtn) return;

    e.preventDefault();
    e.stopPropagation(); // Evita che altri listener (es. navigazione card) vengano triggerati

    const form = deleteBtn.closest('form'); // Il bottone deve essere dentro un form HTMX
    const contactName = deleteBtn.dataset.contactName || 'questo contatto'; // Per un messaggio di conferma migliore

    if (!form) {
      console.error('Modulo HTMX per l"eliminazione non trovato.', deleteBtn);
      Swal.fire('Errore', 'Impossibile procedere con l"eliminazione: modulo non configurato.', 'error');
      return;
    }

    const result = await Swal.fire({
      title: 'Sei sicuro?',
      text: `Vuoi davvero eliminare ${contactName}? Questa azione non può essere annullata.`,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Sì, elimina',
      cancelButtonText: 'Annulla',
      reverseButtons: true,
      customClass: {
        confirmButton: 'bg-red-500 hover:bg-red-700 text-white font-bold py-2 px-4 rounded',
        cancelButton: 'bg-gray-300 hover:bg-gray-400 text-black font-bold py-2 px-4 rounded ml-2'
      },
      buttonsStyling: false
    });

    if (result.isConfirmed) {
      // Invia il form HTMX. La risposta del server (gestita da htmx)
      // includerà HX-Trigger per la conferma admin e l'evento websocket
      // "resource/delete" si occuperà di rimuovere l'elemento dalla UI per tutti.
      form.requestSubmit();
    }
  });
}

// Inizializza subito se questo script viene caricato
// o esporta per un'inizializzazione manuale se preferito (es. in ui.js)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initContactDeleteHandlers);
} else {
  initContactDeleteHandlers();
}
