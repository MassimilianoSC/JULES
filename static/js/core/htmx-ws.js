/**
 * Bridge per connettere i messaggi WebSocket in arrivo a HTMX.
 * Questo modulo ascolta i messaggi sull'istanza globale WebSocket e, se
 * contengono istruzioni specifiche per HTMX (come HX-Trigger), le esegue.
 */
import { ws } from './websocket.js'; // Importa l'istanza WebSocket dal modulo core

// Aggiunge un listener CORRETTO per l'evento 'message' del WebSocket.
// Questa è la correzione principale per l'errore 'addEventListener'.
ws.addEventListener('message', function(event) {
    // Ignora eventi vuoti
    if (!event.data) {
        return;
    }

    try {
        const data = JSON.parse(event.data);

        // Controlla se il messaggio dal server contiene un header 'HX-Trigger'.
        // Questo è un pattern potente che permette al server di scatenare
        // eventi e comportamenti sul client in modo asincrono.
        if (data.headers && data.headers['HX-Trigger']) {
            const triggers = data.headers['HX-Trigger'];
            console.log(`[WS -> HTMX] Ricevuto trigger via WebSocket:`, triggers);
            
            // HX-Trigger può essere una semplice stringa (nome dell'evento)
            // o un oggetto JSON per passare dati più complessi.
            if (typeof triggers === 'string') {
                htmx.trigger('body', triggers, data.detail || {});
            } else if (typeof triggers === 'object') {
                for (const eventName in triggers) {
                    htmx.trigger('body', eventName, triggers[eventName]);
                }
            }
        }
    } catch (e) {
        // Questo blocco catch ignora silenziosamente i messaggi WebSocket
        // che non sono in formato JSON o non sono destinati a HTMX.
        // È normale in un'applicazione che usa i WebSocket per più scopi.
    }
});

console.log('[HTMX-WS] Bridge WebSocket -> HTMX inizializzato e in ascolto.'); 