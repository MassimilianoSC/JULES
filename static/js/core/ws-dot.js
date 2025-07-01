/**
 * Gestione pallino di stato WebSocket
 * Aggiorna l'aspetto e il tooltip del pallino in base agli eventi WebSocket.
 */
import { eventBus } from '/static/js/core/event-bus.js';

(() => {
  const dot = document.getElementById('ws-debugger');
  if (!dot) return;

  const baseClasses = ['fixed', 'bottom-2.5', 'right-2.5', 'z-50', 'w-5', 'h-5', 'rounded-full', 'border-2', 'border-black', 'transition-colors', 'duration-300'];
  const stateMap = {
    open:               { cls: 'bg-green-500', title: 'WebSocket: Connesso' },
    connecting:         { cls: 'bg-yellow-400 animate-pulse', title: 'WebSocket: Connessione in corso...' },
    reconnecting:       { cls: 'bg-yellow-500 animate-pulse', title: 'WebSocket: Riconnessione in corso...' }, // Default title, verrà aggiornato
    closed_cleanly:     { cls: 'bg-gray-400', title: 'WebSocket: Chiuso (normale)' },
    closed_explicitly:  { cls: 'bg-gray-500', title: 'WebSocket: Chiuso (dall\'utente)' },
    closed_unexpectedly:{ cls: 'bg-red-500', title: 'WebSocket: Disconnesso (inaspettato)' },
    error:              { cls: 'bg-orange-600', title: 'WebSocket: Errore rilevato' },
    pending:            { cls: 'bg-gray-300', title: 'WebSocket: In attesa...' } // Stato iniziale o sconosciuto
  };

  function applyStateStyling(stateKey, customTitle = null) {
    const stateConfig = stateMap[stateKey] || stateMap.pending;

    // Rimuovi tutte le classi di colore/animazione precedenti
    Object.values(stateMap).forEach(config => {
        const classesToRemove = config.cls.split(' ');
        dot.classList.remove(...classesToRemove);
    });

    // Aggiungi le nuove classi
    const classesToAdd = stateConfig.cls.split(' ');
    dot.classList.add(...classesToAdd);
    dot.title = customTitle || stateConfig.title;
  }

  // Applica classi base una volta
  dot.className = ''; // Resetta classi esistenti non gestite qui
  dot.classList.add(...baseClasses);


  eventBus.on('ws:connecting', (details) => {
    applyStateStyling('connecting', `WebSocket: Connessione in corso (tentativo ${details.attempt})...`);
  });

  eventBus.on('ws:open', () => {
    applyStateStyling('open');
  });

  eventBus.on('ws:close', (details) => {
    if (details.wasClean || details.code === 1000 || details.code === 1001) {
      applyStateStyling('closed_cleanly');
    } else if (eventBus.wsStatus === 'closed_explicitly') { // Controlla lo stato impostato da closeWebSocket()
      applyStateStyling('closed_explicitly');
    }
    else {
      // Se non è pulita e non è esplicita, e non siamo in 'reconnecting', allora è inaspettata.
      // La logica di 'reconnecting' di solito prende il sopravvento.
      // Questo stato è più un fallback se la riconnessione non parte per qualche motivo.
      if (eventBus.wsStatus !== 'reconnecting') {
         applyStateStyling('closed_unexpectedly', `WebSocket: Disconnesso (Code: ${details.code}, Reason: ${details.reason || 'N/A'})`);
      }
    }
  });

  eventBus.on('ws:reconnecting', (details) => {
    const title = `WebSocket: Riconnessione (tentativo ${details.retries}). Prossima tra ${details.delay / 1000}s. (Code: ${details.code}, Reason: ${details.reason || 'N/A'})`;
    applyStateStyling('reconnecting', title);
  });

  eventBus.on('ws:error', (details) => {
    // Potrebbe essere un errore di connessione o un errore generico.
    // Se siamo già in 'reconnecting', quel titolo è più informativo.
    if (eventBus.wsStatus !== 'reconnecting') {
      applyStateStyling('error', `WebSocket: Errore - ${details.message || 'Vedi console per dettagli.'}`);
    }
  });

  // Aggiorna subito lo stato all'avvio del modulo, basandosi sullo stato corrente dell'eventBus
  // L'eventBus.wsStatus potrebbe non essere ancora impostato se websocket.js non è ancora partito.
  // Quindi, impostiamo a 'pending' e lasciamo che gli eventi lo aggiornino.
  if (eventBus.wsStatus) {
    applyStateStyling(eventBus.wsStatus);
  } else {
    applyStateStyling('pending');
  }

})();