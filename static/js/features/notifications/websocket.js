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
  // message is the full object from eventBus, data is nested: { type: "resource/add", data: { item_type, item_id, user_id, ... } }
  const eventData = message.data || {};
  const { item_type, item_id, user_id: source_user_id, data_filter_criteria } = eventData;

  const currentUserId = document.body.dataset.userId;
  const currentUserRole = document.body.dataset.userRole;

  saveDebugLog(`[WS] Ricevuto evento resource/${event}: ` + JSON.stringify(eventData, null, 2));

  // UI Refresh Logic - This should happen for all users, including the one who made the change,
  // as their direct HTMX swap might not be the list itself.
  // However, the server's direct response to an admin's action (e.g. new row, updated row) might already handle their UI.
  // This WebSocket-triggered refresh is primarily for *other* clients.

  let listElementId;
  let listRefreshUrl;

  if (item_type === 'ai_news') {
    listElementId = 'ai-news-list'; // ID of the ai_news list container
    listRefreshUrl = '/ai-news/list'; // URL to fetch the updated ai_news list partial
  } else if (item_type === 'link') {
    listElementId = 'links-list'; // ID of the links list container
    listRefreshUrl = '/links/list';   // URL to fetch the updated links list partial
  }
  // Add other resource types as needed

  if (listElementId && listRefreshUrl) {
    const listElement = document.getElementById(listElementId);
    if (listElement) {
      // Before refreshing, check if data_filter_criteria matches current view (advanced)
      // For now, always refresh if the list element is present.
      // This ensures other users see the changes.
      // The user who made the change might get a more specific update from HTMX direct response.
      console.log(`[WS] Triggering HTMX GET to refresh ${listElementId} from ${listRefreshUrl} due to resource/${event} for ${item_type}`);
      htmx.ajax('GET', listRefreshUrl, {
        target: `#${listElementId}`, // Ensure the target is the container that will be swapped
        swap: 'outerHTML' // Or 'innerHTML' if the URL returns only the content of the list
      });
    }
  }


  // Toast Logic for other users (non-admin, not the source)
  if (source_user_id === currentUserId || currentUserRole === 'admin') {
    saveDebugLog(`[WS] Toast per resource/${event} ignorato: ${source_user_id === currentUserId ? 'utente corrente è la fonte' : 'utente è admin'}`);
    return; // No toast for the user who made the change or for admins (admins get SweetAlerts)
  }

  const itemTitle = eventData.item_title || item_type; // Use item_title if available

  const eventMessages = {
    add: {
      title: 'Nuova Risorsa Aggiunta',
      body: `Un nuovo elemento '${itemTitle}' (${item_type}) è stato aggiunto.`,
      type: 'success'
    },
    update: {
      title: 'Risorsa Aggiornata',
      body: `L'elemento '${itemTitle}' (${item_type}) è stato aggiornato.`,
      type: 'info'
    },
    delete: {
      title: 'Risorsa Eliminata',
      body: `L'elemento '${itemTitle}' (${item_type}) è stato eliminato.`,
      type: 'warning'
    }
  };

  const messageConfig = eventMessages[event]; // event is 'add', 'update', or 'delete'
  if (messageConfig) {
    saveDebugLog(`[WS] Mostro toast per evento resource/${event} a altri utenti`);
    showToast(messageConfig);
    // Badge refresh might also be desired here if not covered by 'new_notification'
    // htmx.trigger('body', 'notifications.refresh');
  }
}

// Aggiungiamo i listener per tutti gli eventi resource
// The event bus emits the full message which includes 'type' and 'data'
// So, when subscribing, the 'message' parameter in the callback will be this full object.
// handleResourceEvent expects the 'event' string ('add', 'update', 'delete') and the 'message.data' part.
eventBus.on('resource/add', (message) => handleResourceEvent('add', message));
eventBus.on('resource/update', (message) => handleResourceEvent('update', message));
eventBus.on('resource/delete', (message) => handleResourceEvent('delete', message)); 