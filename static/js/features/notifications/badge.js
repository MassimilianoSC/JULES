import { eventBus } from "../../core/event-bus.js";

/**
 * Trova tutti i badge che contano le notifiche e registra il refresh.
 * Badge HTML atteso:
 *   <span id="nav-news-badge"
 *         hx-get="/notifiche/count/news"
 *         hx-trigger="notifications.refresh from:body"
 *         hx-swap="innerHTML"
 *         hx-target="this">0</span>
 */
export function initBadges() {
  // 1) Primo caricamento: scatena un refresh di tutti i badge HTMX
  htmx.trigger("body", "notifications.refresh");

  // 2) Il refresh dei badge in risposta a nuove notifiche WebSocket
  // è gestito da `static/js/features/notifications/websocket.js`.
  // Quel file ascolta `new_notification` dall'event bus (emesso da `core/websocket.js`)
  // e poi esegue `htmx.trigger('body', 'notifications.refresh');`.
  // Quindi, un listener separato qui per un evento `notifications/new` è ridondante
  // e potenzialmente confuso se l'evento non viene emesso come previsto.
  // eventBus.on("notifications/new", () => {
  //   log.debug('Evento notifications/new ricevuto, aggiorno i badge.');
  //   htmx.trigger("body", "notifications.refresh");
  // });
}

// auto-bootstrap
initBadges();