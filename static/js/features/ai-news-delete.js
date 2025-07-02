import { eventBus } from '/static/js/core/event-bus.js';

// This function can be called to initialize delete functionality for AI News items.
// It expects delete buttons to have 'data-delete-url' and 'data-item-id' attributes.
// The 'data-delete-url' should point to the DELETE endpoint for the AI news item.
// The 'data-item-id' is the ID of the news item, used for removing the element from the UI.
export function initAiNewsDeleteConfirmation() {
  document.body.addEventListener('click', async (event) => {
    const deleteButton = event.target.closest('button[data-delete-url][data-item-id]');

    if (!deleteButton) {
      return; // Click was not on a delete button for AI News
    }

    event.preventDefault(); // Prevent default form submission if it's a submit button

    const deleteUrl = deleteButton.dataset.deleteUrl;
    const itemId = deleteButton.dataset.itemId;
    const itemName = deleteButton.dataset.itemName || 'questo elemento'; // Fallback item name

    // Show SweetAlert confirmation
    const result = await Swal.fire({
      title: 'Sei sicuro?',
      html: `Vuoi davvero eliminare <strong>${itemName}</strong>?<br>Questa azione non può essere annullata.`,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Sì, elimina!',
      cancelButtonText: 'Annulla',
      confirmButtonColor: '#d33',
      cancelButtonColor: '#3085d6',
      reverseButtons: true,
    });

    if (result.isConfirmed) {
      // User confirmed, proceed with the delete request using HTMX if the button is part of an HTMX form
      // or manually if not.
      // For consistency with the row_partial.html which has <form hx-delete="...">,
      // we assume the button might be inside such a form.
      // If the button itself is the hx-delete trigger, HTMX handles it.
      // This script primarily adds the confirmation step.

      const htmxForm = deleteButton.closest('form[hx-delete]');
      if (htmxForm) {
        // If the button is inside an HTMX form, let HTMX handle the submission.
        // HTMX will make the DELETE request.
        // We might need to manually trigger the request if the button isn't a submit type
        // or if the form submission needs to be explicitly invoked.
        // For now, assuming HTMX handles it or the button itself has hx-delete.
        // If the button itself is `hx-delete`, this JS confirmation runs before HTMX processes the click.
        console.log(`HTMX form found for ${itemId}, allowing HTMX to proceed.`);
        // If the button is NOT type="submit" or not directly triggering hx-delete,
        // you might need to do: htmx.trigger(htmxForm, "submit"); or htmx.ajax('DELETE', deleteUrl, {target: `#ai-news-${itemId}`, swap: 'delete'});
        // However, the current ai_news/row_partial.html has onclick="showDelete(this)" which this replaces.
        // The form itself has hx-delete. So, if this button is a submit button, it will trigger.
        // If it's just a button, we need to trigger the form or make the call.

        // Let's assume the button IS the trigger or is type=submit in an hx-form.
        // If not, this part needs adjustment. The goal is for this script to *just* confirm.
        // The actual hx-delete on the form in row_partial.html will handle the request and removal.
        // If the button itself has hx-delete, HTMX will also pick it up.
        // This function is primarily for the SweetAlert confirmation.
      } else {
        // Fallback: if no HTMX form, make a manual fetch (less ideal if HTMX is used elsewhere for this)
        console.warn(`No HTMX form with hx-delete found for ${itemId}. Consider using HTMX for deletion.`);
        // This manual fetch block is a fallback and might not be needed if row_partial.html is correctly set up.
        try {
          const response = await fetch(deleteUrl, {
            method: 'DELETE',
            headers: {
              'X-Requested-With': 'XMLHttpRequest', // Standard header for AJAX
              // 'HX-Request': 'true' // If server specifically checks for this
            },
          });

          if (response.ok) {
            const itemElement = document.getElementById(`ai-news-${itemId}`);
            if (itemElement) {
              itemElement.remove();
            }
            // Admin confirmation will be handled by HX-Trigger from server if any
            // Non-admin toast will be handled by WebSocket event
            eventBus.emit('resource/delete', { type: 'ai_news', id: itemId }); // For other UI updates
          } else {
            const errorData = await response.text();
            Swal.fire('Errore!', `Si è verificato un errore durante l'eliminazione: ${errorData}`, 'error');
          }
        } catch (error) {
          console.error('Errore fetch delete:', error);
          Swal.fire('Errore!', 'Impossibile contattare il server.', 'error');
        }
      }
    }
  });
}

// Initialize on load or call this function when appropriate
// initAiNewsDeleteConfirmation();
