/**
 * Gestisce le conferme per l'admin, ora come modale centrale,
 * con stile personalizzato e gestione degli errori migliorata.
 */

// Abilita i log solo in ambiente di sviluppo per un codice di produzione più pulito.
const DEBUG_MODE = true;  // Forziamo i log per debug

if (DEBUG_MODE) {
  console.log('[Confirmations] Modulo in ascolto per eventi "showAdminConfirmation".');
}

function saveDebugLog(message) {
  console.log(message);  // Forziamo il log in console
  const logs = JSON.parse(sessionStorage.getItem('debug_logs') || '[]');
  logs.push(message);
  sessionStorage.setItem('debug_logs', JSON.stringify(logs));
}

// Aggiungiamo un listener per tutti gli eventi HX-Trigger per debug
document.body.addEventListener('htmx:afterOnLoad', function(evt) {
  console.log('[Debug] htmx:afterOnLoad triggered', evt);
});

document.body.addEventListener('htmx:afterRequest', function(evt) {
  console.log('[Debug] htmx:afterRequest triggered', evt);
  console.log('[Debug] Response headers:', evt.detail.xhr.getAllResponseHeaders());
});

document.body.addEventListener('showAdminConfirmation', (evt) => {
  console.log('[DEBUG-FRONTEND] Evento showAdminConfirmation completo:', evt);
  console.log('[DEBUG-FRONTEND] evt.detail:', evt.detail);
  console.log('[DEBUG-FRONTEND] evt.detail.showAdminConfirmation:', evt.detail.showAdminConfirmation);
  
  const { title, message, level = 'success', duration = 3000 } = evt.detail || {};
  const userRole = document.body.dataset.userRole;

  saveDebugLog('[Admin Confirmation] Ricevuto evento: ' + JSON.stringify({
    title,
    message,
    level,
    duration,
    userRole
  }, null, 2));

  // Mostra la conferma solo se l'utente è admin
  if (userRole !== 'admin') {
    saveDebugLog('[Admin Confirmation] Ignorato: utente non admin');
    return;
  }

  // Se il payload dell'evento è malformato, mostra un fallback generico all'utente.
  if (!title || !message) {
    saveDebugLog('[Admin Confirmation] Payload malformato: ' + JSON.stringify(evt.detail));
    Swal.fire({
      title: 'Operazione Completata',
      text: 'L\'operazione è stata completata con successo.',
      icon: 'success',
      timer: 2000,
      showConfirmButton: false,
      position: 'center'
    });
    return;
  }
  
  saveDebugLog('[Admin Confirmation] Mostro conferma admin');
  // Usa una modale centrale con stile personalizzato.
  Swal.fire({
    title: title,
    text: message,
    icon: level, // 'success', 'info', 'warning'
    timer: duration,
    timerProgressBar: true, // Feedback visivo per il countdown
    showConfirmButton: false,
    position: 'center',
    width: '400px',
    // Classi CSS e stili per una maggiore coerenza con il design dell'app
    customClass: {
      popup: 'admin-confirmation-modal',
      title: 'admin-confirmation-title',
      timerProgressBar: 'admin-confirmation-timer'
    },
    backdrop: `rgba(0,0,10,0.4)`, // Overlay più scuro per maggiore focus
  });
});

// Gestione rimozione elementi dalla UI
document.body.addEventListener('removeElement', (evt) => {
  console.log('[Debug] removeElement event received', evt);
  const selector = evt.detail;
  if (!selector) {
    saveDebugLog('[Remove Element] Nessun selettore fornito');
    return;
  }

  saveDebugLog(`[Remove Element] Rimuovo elemento: ${selector}`);
  const element = document.querySelector(selector);
  if (element) {
    element.remove();
  } else {
    saveDebugLog(`[Remove Element] Elemento non trovato: ${selector}`);
  }
}); 