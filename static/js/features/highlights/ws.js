import { eventBus } from "/static/js/core/event-bus.js";

function refreshHighlights() {
  const target = document.getElementById('home-page-highlights');
  if (target) {
    htmx.ajax("GET", "/home/highlights/partial", { target: target });
  }
}

// Ascolto gli eventi corretti dall'event bus
eventBus.on('resource/add', refreshHighlights);
eventBus.on('resource/delete', refreshHighlights);
eventBus.on('resource/update', refreshHighlights); 