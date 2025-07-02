// static/js/features/news-delete.js
/**
 * Inizializza i gestori per i pulsanti di eliminazione delle news.
 * Utilizza HTMX per la richiesta DELETE dopo conferma tramite SweetAlert.
 */
export function initNewsDeleteHandlers() {
  document.addEventListener('click', async (e) => {
    const deleteBtn = e.target.closest('.btn-delete-news'); // Selettore specifico
    if (!deleteBtn) return;

    e.preventDefault();
    e.stopPropagation();

    const form = deleteBtn.closest('form');
    const newsTitle = deleteBtn.dataset.newsTitle || 'questa news';

    if (!form) {
      console.error('Modulo HTMX per l"eliminazione non trovato.', deleteBtn);
      Swal.fire('Errore', 'Impossibile procedere con l"eliminazione: modulo non configurato.', 'error');
      return;
    }

    const result = await Swal.fire({
      title: 'Sei sicuro?',
      text: `Vuoi davvero eliminare la news "${newsTitle}"? Questa azione non può essere annullata.`,
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
      form.requestSubmit();
    }
  });
}

// Inizializza subito
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initNewsDeleteHandlers);
} else {
  initNewsDeleteHandlers();
}
