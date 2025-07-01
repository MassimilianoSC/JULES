// --- Gestione CONTATTI ---
if (payload.type === 'new_notification' && payload.data && payload.data.tipo === 'contatto') {
  const branch = payload.data.branch === '*' ? 'Tutti' : (payload.data.branch || '');
  if (payload.data.message && payload.data.message.includes('eliminato')) {
    Toastify({
      text: `Contatto eliminato: "${payload.data.title || ''}" (${branch})`,
      duration: 4000,
      gravity: 'top',
      position: 'right',
      backgroundColor: 'linear-gradient(to right, #ef4444, #f87171)'
    }).showToast();
  } else if (payload.data.message && payload.data.message.includes('modificato') && payload.data.isUpdate) {
    Toastify({
      text: `Contatto modificato: "${payload.data.title || ''}" (${branch})\nI destinatari potrebbero essere cambiati.`,
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
            text: `È stato pubblicato un nuovo contatto: ${payload.data.title || ''}${branch ? ' (' + branch + ')' : ''}`,
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