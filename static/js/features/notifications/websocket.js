/**
 * Gestore delle notifiche ricevute via WebSocket.
 * Ascolta l'event bus e chiama la funzione 'showToast'.
 */
import { eventBus } from "/static/js/core/event-bus.js";
import { showToast } from "./toast.js";

console.log('[Notifications-WS] In ascolto per eventi "new_notification".');

function saveDebugLog(message) {
  const logs = JSON.parse(sessionStorage.getItem('debug_logs') || '[]');
  logs.push(message);
  sessionStorage.setItem('debug_logs', JSON.stringify(logs));
  console.log(message);
}

eventBus.on('new_notification', (message) => {
  const { title, body, level, source_user_id } = message.data || {};
  const currentUserId = document.body.dataset.userId;
  const currentUserRole = document.body.dataset.userRole;

  saveDebugLog('[WS] Ricevuta notifica: ' + JSON.stringify({
    title,
    body,
    level,
    source_user_id,
    currentUserId,
    currentUserRole
  }, null, 2));

  // Non mostrare il toast se l'utente corrente è quello che ha eseguito l'azione
  // o se l'utente è admin
  if (source_user_id === currentUserId || currentUserRole === 'admin') {
    saveDebugLog(`[WS] Toast ignorato: ${source_user_id === currentUserId ? 'utente corrente è la fonte' : 'utente è admin'}`);
    return;
  }

  if (title && body) {
    saveDebugLog('[WS] Mostro toast per destinatario');
    showToast({
        title: title,
        body: body,
        type: level || 'info',
    });
    htmx.trigger('body', 'notifications.refresh');
  }
});

// Funzione helper per gestire gli eventi resource
function handleResourceEvent(event, message) {
  const { item, source_user_id } = message || {};
  const currentUserId = document.body.dataset.userId;
  const currentUserRole = document.body.dataset.userRole;

  saveDebugLog(`[WS] Ricevuto evento resource/${event}: ` + JSON.stringify({
    item,
    source_user_id,
    currentUserId,
    currentUserRole
  }, null, 2));

  // Non mostrare il toast se l'utente corrente è quello che ha eseguito l'azione
  // o se l'utente è admin
  if (source_user_id === currentUserId || currentUserRole === 'admin') {
    saveDebugLog(`[WS] Toast resource ignorato: ${source_user_id === currentUserId ? 'utente corrente è la fonte' : 'utente è admin'}`);
    return;
  }

  const eventMessages = {
    add: {
      title: 'Nuova Risorsa',
      body: `È stato aggiunto un nuovo elemento di tipo: ${item?.type}`,
      type: 'success'
    },
    update: {
      title: 'Risorsa Aggiornata',
      body: `È stato modificato un elemento di tipo: ${item?.type}`,
      type: 'info'
    },
    delete: {
      title: 'Risorsa Eliminata',
      body: `È stato eliminato un elemento di tipo: ${item?.type}`,
      type: 'warning'
    }
  };

  const messageConfig = eventMessages[event];
  if (messageConfig) {
    saveDebugLog(`[WS] Mostro toast per evento resource/${event}`);
    showToast(messageConfig);
  }
}

// Aggiungiamo i listener per tutti gli eventi resource
eventBus.on('resource/add', (message) => handleResourceEvent('add', message));
eventBus.on('resource/update', (message) => handleResourceEvent('update', message));
eventBus.on('resource/delete', (message) => handleResourceEvent('delete', message)); 