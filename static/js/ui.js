// --- Gestione CONTATTI --- (Logica preesistente, da revisionare in futuro)
// if (payload.type === 'new_notification' && payload.data && payload.data.tipo === 'contatto') {
//   const branch = payload.data.branch === '*' ? 'Tutti' : (payload.data.branch || '');
//   if (payload.data.message && payload.data.message.includes('eliminato')) {
//     Toastify({
//       text: `Contatto eliminato: "${payload.data.title || ''}" (${branch})`,
//       duration: 4000,
//       gravity: 'top',
//       position: 'right',
//       backgroundColor: 'linear-gradient(to right, #ef4444, #f87171)'
//     }).showToast();
//   } else if (payload.data.message && payload.data.message.includes('modificato') && payload.data.isUpdate) {
//     Toastify({
//       text: `Contatto modificato: "${payload.data.title || ''}" (${branch})\nI destinatari potrebbero essere cambiati.`,
//       duration: 4000,
//       gravity: 'top',
//       position: 'right',
//       backgroundColor: 'linear-gradient(to right, #fbbf24, #f59e42)'
//     }).showToast();
//   } else {
//     fetch('/notifiche/inline')
//       .then(response => response.text())
//       .then(html => {
//         if (html.includes(payload.data.id)) {
//           Toastify({
//             text: `È stato pubblicato un nuovo contatto: ${payload.data.title || ''}${branch ? ' (' + branch + ')' : ''}`,
//             duration: 4000,
//             gravity: 'top',
//             position: 'right',
//             backgroundColor: 'linear-gradient(to right, #00b09b, #96c93d)'
//           }).showToast();
//         }
//       });
//   }
//   if (window.htmx) {
//     htmx.trigger(document.body, 'refreshContattiBadgeEvent');
//   }
// }

/**
 * Gestore Globale per le conferme Admin e altre azioni triggerate da HX-Trigger.
 * Cerca specificamente `showAdminConfirmation` e `closeModal` nel payload HX-Trigger.
 */
document.addEventListener('htmx:afterRequest', function(evt) {
  if (evt.detail.xhr && evt.detail.xhr.getResponseHeader('HX-Trigger')) {
    try {
      const triggerData = JSON.parse(evt.detail.xhr.getResponseHeader('HX-Trigger'));

      // Gestione Conferma Admin (NON-TOAST)
      if (triggerData.showAdminConfirmation) {
        const conf = triggerData.showAdminConfirmation;
        Swal.fire({
          title: conf.title || 'Azione Completata',
          text: conf.message,
          icon: conf.level || 'success',
          timer: conf.duration || 3000,
          showConfirmButton: false,
          customClass: {
            popup: 'admin-confirmation-popup' // Per eventuale styling specifico
          }
        });
      }

      // Gestione Chiusura Modale
      if (triggerData.closeModal === true || triggerData.closeModal === "true") {
        // Assumendo che la modale abbia un ID 'modal' e un metodo 'hide' o simile.
        // Questo potrebbe necessitare di un selettore più specifico o di un sistema di gestione modali.
        // Per ora, un esempio generico:
        const modalElement = document.getElementById('modal'); // O il selettore della tua modale principale
        if (modalElement && typeof bootstrap !== 'undefined' && bootstrap.Modal.getInstance(modalElement)) {
          bootstrap.Modal.getInstance(modalElement).hide();
        } else if (modalElement && modalElement.classList.contains('modal-open')) { // Fallback per modali custom
           modalElement.classList.remove('modal-open');
        } else {
            // Potrebbe essere necessario un meccanismo più robusto per chiudere la modale
            // Se si usa una libreria specifica o un componente custom.
            console.log("Tentativo di chiudere la modale, ma nessuna modale standard trovata o istanza non recuperabile.");
        }
      }

      // Gestione Redirect (esempio da `links.py` per `create_link`)
      if (triggerData["redirect-to-links"]) {
        window.location.pathname = triggerData["redirect-to-links"];
      }
      if (triggerData["redirectToContatti"]) { // Aggiunto per coerenza con create_contact
        window.location.pathname = triggerData["redirectToContatti"];
      }


    } catch (e) {
      console.error('Errore nel parsing di HX-Trigger JSON:', e, evt.detail.xhr.getResponseHeader('HX-Trigger'));
    }
  }
});

// Altra logica UI preesistente può rimanere qui sotto...