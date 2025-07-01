/**
 * Event bus centralizzato per la comunicazione tra moduli
 */

/* ------------------------------------------------------------------
 * event-bus.js  –  micro‑bus senza dipendenze esterne
 * API identica a mitt:
 *   bus.on(event, handler)
 *   bus.off(event, handler)
 *   bus.emit(event, payload)
 * -----------------------------------------------------------------*/

const listeners = new Map();
export const busImpl = {
  on(e,f) { let a=listeners.get(e)||listeners.set(e,[]).get(e); a.push(f); },
  off(e,f) { const a=listeners.get(e)||[]; listeners.set(e,a.filter(x=>x!==f)); },
  emit(e,p) { (listeners.get(e)||[]).slice().forEach(fn=>fn(p)); }
};

class EventBus {
  on(e,fn) { busImpl.on(e,fn); }
  off(e,fn) { busImpl.off(e,fn); }
  emit(e,p) { busImpl.emit(e,p); }
}

export const eventBus = new EventBus();  // 👉 quello che tutto il progetto già usa

// stato connessione WS (sticky)
eventBus.wsStatus = 'pending';           // 'open' | 'close' | 'error'

/* alias per nuovo codice / snippet esterni --------------------- */
export const bus = eventBus;             // import { bus } …  funzionerà
export default eventBus;                 // import busDefault … funzionerà

// Compatibilità legacy con tracciamento accessi
if (!('eventBus' in window)) {
    Object.defineProperty(window, 'eventBus', {
        get() {
            console.warn('[Deprecato] usa import { eventBus } from "/static/js/core/event-bus.js"');
            console.trace();  // Aggiungo stack trace automatico
            return eventBus;
        },
        set() {
            console.warn('[Bloccato] non sovrascrivere eventBus globale');
        },
    });
} 