/**
 * Gestisce i redirect dopo le azioni CRUD con SweetAlert2
 */

document.body.addEventListener('htmx:afterOnLoad', function(evt) {
    // Controlla se c'è un trigger HX con showSwal e redirectAfterSwal
    const triggerHeader = evt.detail.xhr.getResponseHeader("HX-Trigger");
    if (!triggerHeader) return;
    
    try {
        const triggers = JSON.parse(triggerHeader);
        if (triggers.showSwal && triggers.redirectAfterSwal) {
            // Mostra SweetAlert2 e poi fai il redirect
            Swal.fire(triggers.showSwal).then(() => {
                window.location.href = triggers.redirectAfterSwal;
            });
        }
    } catch (e) {
        console.error('Errore nel parsing dei trigger HX:', e);
    }
}); 