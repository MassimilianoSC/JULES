/**
 * Punto di ingresso (entry-point) per i moduli JavaScript core dell'applicazione.
 * Il suo unico scopo è importare gli altri moduli essenziali per avviarli.
 */

// Importa il gestore WebSocket. L'atto stesso di importarlo
// avvierà la logica di connessione contenuta al suo interno.
import '/static/js/core/websocket.js';

// Importa il gestore per il "pallino" di stato del WebSocket.
// Si metterà in ascolto degli eventi emessi da websocket.js.
import '/static/js/core/ws-dot.js';

// Importa il bridge per HTMX, se necessario per la comunicazione
// da WebSocket a HTMX.
import '/static/js/core/htmx-ws.js';

// Importa il gestore dei redirect dopo le azioni CRUD
import '/static/js/core/redirects.js';

console.log('[Bootstrap] Moduli core inizializzati.'); 