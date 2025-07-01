/**
 * Gestore WebSocket centralizzato, robusto e compatibile.
 * Fornisce un'unica istanza stabile della connessione per tutta l'applicazione.
 * Include gestione degli errori, riconnessione automatica con backoff,
 * heartbeat e notifiche toast per lo stato della connessione.
 */
import { eventBus } from './event-bus.js';
import { showToast } from '../features/notifications/toast.js';
import logger from './logger.js'; // Importa il logger

const log = logger.module('WS'); // Crea un'istanza del logger per questo modulo

// --- Configurazione ---
const HEARTBEAT_INTERVAL = 25000; // Intervallo per inviare un heartbeat
const HEARTBEAT_TIMEOUT = 10000;  // Timeout per ricevere ack dell'heartbeat prima di chiudere
const MAX_RECONNECT_DELAY = 30000; // Massimo ritardo per la riconnessione (30s)
const INITIAL_RECONNECT_DELAY = 1000; // Ritardo iniziale per la riconnessione (1s)

// --- Stato Interno del Modulo ---
let wsInstance = null;
let retries = 0; // Contatore dei tentativi di riconnessione
let heartbeatIntervalTimer = null;
let heartbeatTimeoutTimer = null;
let explicitlyClosed = false; // Flag per indicare se la chiusura è stata richiesta esplicitamente

function connect() {
    if (explicitlyClosed) {
        log.info('Connessione chiusa esplicitamente, non si tenta di riconnettere.');
        return;
    }

    clearInterval(heartbeatIntervalTimer);
    clearTimeout(heartbeatTimeoutTimer);

    const url = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
    log.info(`Inizio connessione a ${url} (Tentativo: ${retries + 1})...`);
    eventBus.wsStatus = 'connecting';
    eventBus.emit('ws:connecting', { attempt: retries + 1 });


    try {
        wsInstance = new WebSocket(url);
    } catch (error) {
        log.error('Errore istanziazione WebSocket:', error);
        // Questo errore è sincrono e di solito indica un problema con l'URL o la sicurezza
        // Gestiamo come un errore che impedisce la connessione e tentiamo di riconnettere
        handleConnectionError(error);
        return;
    }

    wsInstance.onopen = () => {
        if (retries > 0) {
            showToast({ title: "Connessione Ristabilita", body: "La connessione WebSocket è di nuovo attiva.", type: 'success' });
        }
        log.info('Connessione stabilita.');
        retries = 0;
        explicitlyClosed = false; // Resetta in caso di connessione riuscita
        eventBus.wsStatus = 'open';
        eventBus.emit('ws:open');
        startHeartbeat();
    };

    wsInstance.onclose = (event) => {
        clearInterval(heartbeatIntervalTimer);
        clearTimeout(heartbeatTimeoutTimer);
        log.warn('Connessione chiusa.', { code: event.code, reason: event.reason, wasClean: event.wasClean });

        eventBus.emit('ws:close', { // Emettiamo sempre ws:close per informare i listener
            retries,
            delay: 0, // Sarà impostato dal reconnecting se avviene
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean
        });

        if (explicitlyClosed || event.code === 1000 || event.code === 1001) {
            log.info('Chiusura pulita o esplicita, nessuna riconnessione automatica.');
            eventBus.wsStatus = (event.code === 1000 || event.code === 1001) ? 'closed_cleanly' : 'closed_explicitly';
            // wsInstance = null; // Rimuovi riferimento
            return;
        }

        // Se non è una chiusura pulita o esplicita, procedi con la riconnessione
        retries++;
        const delay = Math.min(MAX_RECONNECT_DELAY, INITIAL_RECONNECT_DELAY * (2 ** (retries -1) ));

        log.info(`Riconnessione (tentativo ${retries}) tra ${delay / 1000}s...`);
        eventBus.wsStatus = 'reconnecting';
        eventBus.emit('ws:reconnecting', { retries, delay, code: event.code, reason: event.reason });

        if (retries > 1) { // Mostra toast dopo il primo tentativo fallito
            showToast({
                title: "Connessione Persa",
                body: `Si tenterà di riconnettere (${retries}). Prossimo tentativo tra ${delay / 1000}s.`,
                type: 'warning',
                duration: delay > 5000 ? delay - 1000 : 5000 // Toast più lungo per attese lunghe
            });
        }
        setTimeout(connect, delay);
    };

    wsInstance.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);

            if (message.type === 'heartbeat' && message.status === 'acknowledged') {
                handleHeartbeatAck();
                return;
            }
            
            if (message.type === 'error' || message.status === 'error') {
                log.error('Messaggio di errore applicativo ricevuto:', message);
                const errorMessage = message.data?.message || message.message || "Errore sconosciuto ricevuto dal server.";
                const errorTitle = message.data?.title || "Errore dal Server";
                showToast({ title: errorTitle, body: errorMessage, type: 'error' });
                eventBus.emit('ws:message:error', {
                    message: errorMessage,
                    title: errorTitle,
                    code: message.data?.code,
                    details: message.data || message
                });
                return;
            }

            if (message.type) {
                // Inoltra `message.data` se esiste e contiene le proprietà attese,
                // altrimenti inoltra l'intero oggetto `message` per flessibilità.
                // Questo assume che se `data` esiste, è il payload principale.
                const payload = (typeof message.data !== 'undefined') ? message.data : message;
                eventBus.emit(message.type, payload);
            } else {
                log.warn('Messaggio ricevuto senza un "type":', message);
            }
        } catch (e) {
            log.warn('Ignorato messaggio non JSON o malformato:', event.data, e);
        }
    };

    wsInstance.onerror = (errorEvent) => {
        // Questo evento di solito precede 'onclose'.
        log.error('Errore WebSocket rilevato:', errorEvent);
        eventBus.wsStatus = 'error'; // Stato transitorio, onclose gestirà la riconnessione
        eventBus.emit('ws:error', { error: errorEvent, message: "Errore di connessione WebSocket." });
        // Non mostriamo toast qui, onclose lo gestirà in modo più informativo.
        // wsInstance.close(); // Assicura che onclose sia chiamato se l'errore non lo fa automaticamente
    };
}


function handleConnectionError(error) {
    // Funzione chiamata quando WebSocket constructor fallisce o per altri errori critici pre-onclose
    clearInterval(heartbeatIntervalTimer);
    clearTimeout(heartbeatTimeoutTimer);
    log.error('Errore critico di connessione:', error);

    eventBus.emit('ws:error', { error, message: "Impossibile stabilire la connessione WebSocket." });

    if (explicitlyClosed) return;

    retries++;
    const delay = Math.min(MAX_RECONNECT_DELAY, INITIAL_RECONNECT_DELAY * (2 ** (retries - 1)));

    log.info(`Riconnessione (tentativo ${retries} post-errore critico) tra ${delay / 1000}s...`);
    eventBus.wsStatus = 'reconnecting';
    eventBus.emit('ws:reconnecting', { retries, delay, code: null, reason: 'Critical connection error' });

    if (retries > 1) {
        showToast({
            title: "Errore Connessione",
            body: `Impossibile connettersi. Si ritenterà (${retries}). Prossimo tentativo tra ${delay / 1000}s.`,
            type: 'error',
            duration: delay > 5000 ? delay - 1000 : 5000
        });
    }
    setTimeout(connect, delay);
}


function startHeartbeat() {
    clearInterval(heartbeatIntervalTimer); // Pulisci qualsiasi heartbeat precedente
    clearTimeout(heartbeatTimeoutTimer);  // e il suo timeout

    heartbeatIntervalTimer = setInterval(() => {
        if (wsInstance?.readyState === WebSocket.OPEN) {
            log.debug('Invio heartbeat...');
            wsInstance.send(JSON.stringify({ type: 'heartbeat', timestamp: Date.now() }));

            // Imposta un timeout per l'ack dell'heartbeat
            clearTimeout(heartbeatTimeoutTimer); // Pulisci timeout precedente se ancora attivo
            heartbeatTimeoutTimer = setTimeout(() => {
                log.warn('Timeout heartbeat! L\'ack non è stato ricevuto in tempo. Chiudo la connessione.');
                if (wsInstance) wsInstance.close(); // Questo scatenerà onclose e la logica di riconnessione
            }, HEARTBEAT_TIMEOUT);
        } else {
            log.debug('Heartbeat saltato, WebSocket non OPEN.');
            // Potrebbe essere necessario gestire questo caso, es. forzando una riconnessione se lo stato è anomalo per troppo tempo.
            // Per ora, la logica di onclose dovrebbe coprire i casi di disconnessione.
        }
    }, HEARTBEAT_INTERVAL);
}

function handleHeartbeatAck() {
    log.debug('Heartbeat acknowledged.');
    clearTimeout(heartbeatTimeoutTimer); // Annulla il timeout poiché abbiamo ricevuto l'ack
}

// --- API Pubblica del Modulo ---
export function getWS() {
    if (!wsInstance || wsInstance.readyState === WebSocket.CLOSED || wsInstance.readyState === WebSocket.CLOSING) {
        // Se non c'è istanza, o è chiusa/in chiusura, (ri)connetti.
        // Questo gestisce anche il caso in cui la connessione viene chiusa esplicitamente
        // e poi si tenta di ottenerla di nuovo.
        explicitlyClosed = false; // Permetti la riconnessione se getWS viene chiamato di nuovo
        connect();
    }
    return wsInstance;
}

export const ws = getWS(); // Esporta una singola istanza, inizializzandola se necessario

export function closeWebSocket(code = 1000, reason = "Chiusura richiesta dall'applicazione") {
    if (wsInstance && wsInstance.readyState === WebSocket.OPEN) {
        log.info(`Chiusura esplicita della connessione WebSocket (code: ${code}, reason: ${reason}).`);
        explicitlyClosed = true;
        wsInstance.close(code, reason);
    } else {
        log.info('Nessuna connessione WebSocket attiva da chiudere esplicitamente o già in chiusura.');
        explicitlyClosed = true; // Assicura che non si riconnetta se era in fase di tentativo
        if (wsInstance) {
             // Se l'istanza esiste ma non è OPEN (es. CONNECTING), impostare explicitlyClosed
             // dovrebbe prevenire la logica di riconnessione in onclose.
        }
    }
}