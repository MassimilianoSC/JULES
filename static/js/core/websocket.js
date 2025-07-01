/**
 * Gestore WebSocket centralizzato, robusto e compatibile.
 * Fornisce un'unica istanza stabile della connessione per tutta l'applicazione.
 */
import { eventBus } from './event-bus.js';

// --- Configurazione ---
const HEARTBEAT_INTERVAL = 25000;
const HEARTBEAT_TIMEOUT = 10000;

// --- Stato Interno del Modulo ---
let wsInstance = null;
let retries = 0;
let heartbeatIntervalTimer = null;
let heartbeatTimeoutTimer = null;

function connect() {
    clearInterval(heartbeatIntervalTimer);
    clearTimeout(heartbeatTimeoutTimer);

    const url = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
    console.log(`[WS] Inizio connessione a ${url}...`);

    wsInstance = new WebSocket(url);

    wsInstance.onopen = () => {
        console.log('[WS] Connessione stabilita.');
        retries = 0;
        eventBus.wsStatus = 'open';
        eventBus.emit('ws:open');
        startHeartbeat();
    };

    wsInstance.onclose = () => {
        clearInterval(heartbeatIntervalTimer);
        clearTimeout(heartbeatTimeoutTimer);
        const delay = Math.min(5_000, 250 * 2 ** retries++);   // 250 ms → 5 s
        setTimeout(connect, delay);
        eventBus.wsStatus = 'close';
        eventBus.emit('ws:close', { retries, delay });
    };

    wsInstance.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);

            if (message.type === 'heartbeat' && message.status === 'acknowledged') {
                handleHeartbeatAck();
                return;
            }
            
            // Inoltra tutti i messaggi con un 'type' sull'event bus
            if (message.type) {
                eventBus.emit(message.type, message);
            }
        } catch (e) {
            // Ignora messaggi non JSON
        }
    };

    wsInstance.onerror = (error) => {
        console.error('[WS] Errore WebSocket:', error);
        eventBus.wsStatus = 'error';
        eventBus.emit('ws:error');
    };
}

function startHeartbeat() {
    clearInterval(heartbeatIntervalTimer);
    heartbeatIntervalTimer = setInterval(() => {
        if (wsInstance?.readyState === WebSocket.OPEN) {
            wsInstance.send(JSON.stringify({ type: 'heartbeat' }));
            heartbeatTimeoutTimer = setTimeout(() => wsInstance.close(), HEARTBEAT_TIMEOUT);
        }
    }, HEARTBEAT_INTERVAL);
}

function handleHeartbeatAck() {
    clearTimeout(heartbeatTimeoutTimer);
}

// --- Esportazioni per Compatibilità ---
export function getWS() {
    if (!wsInstance) {
        connect();
    }
    return wsInstance;
}

export const ws = getWS(); 