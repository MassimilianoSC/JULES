import { showToast } from '/static/js/features/notifications/toast.js';
import { eventBus } from '/static/js/core/event-bus.js';

export function initDeleteHandlers() {
  document.addEventListener('click', async e => {
    const deleteBtn = e.target.closest('[data-delete-url]');
    if (!deleteBtn) return;

    e.preventDefault();
    const linkId = deleteBtn.dataset.linkId;
    const form = deleteBtn.closest('form');
    
    if (!form) {
      console.error('Form HTMX non trovato');
      return;
    }

    const result = await Swal.fire({
      title: 'Sei sicuro?',
      text: 'Questa azione non può essere annullata',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Sì, elimina',
      cancelButtonText: 'Annulla',
      reverseButtons: true
    });

    if (result.isConfirmed) {
      form.requestSubmit();
    }
  });
} 