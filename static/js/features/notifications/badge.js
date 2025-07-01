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
  // 1) Primo caricamento
  htmx.trigger("body", "notifications.refresh");

  // 2) Ogni nuova notifica -> refresh badge
  eventBus.on("notifications/new", () => {
    htmx.trigger("body", "notifications.refresh");
  });
}

// auto-bootstrap
initBadges(); 