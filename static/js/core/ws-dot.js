/**
 * Gestione pallino di stato WebSocket
 */

import { eventBus } from '/static/js/core/event-bus.js';

(() => {  // Wrapper IIFE
  const dot = document.getElementById('ws-debugger');
  if (!dot) return;

  function paint(state) {
    const map = {
      open:  ['bg-green-500', 'WebSocket: connesso'],
      close: ['bg-red-500',   'WebSocket: disconnesso'],
      error: ['bg-gray-400',  'WebSocket: errore'],
      pending: ['bg-gray-400','WebSocket: in attesa…']
    };
    const [cls,title] = map[state] ?? map.pending;
    dot.classList.remove('bg-green-500','bg-red-500','bg-gray-400');
    dot.classList.add(cls);
    dot.title = title;
  }

  /* 1) ascolta eventi futuri */
  eventBus.on('ws:open',  () => paint('open'));
  eventBus.on('ws:close', () => paint('close'));
  eventBus.on('ws:error', () => paint('error'));

  /* 2) aggiorna subito secondo lo stato già noto */
  paint(eventBus.wsStatus);
})(); 