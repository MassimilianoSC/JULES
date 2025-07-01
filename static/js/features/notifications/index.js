import { initToasts } from "./toast.js";
import "./badge.js";        // importa per side-effect
import "./websocket.js";    // importa per side-effect
import "./confirmations.js";

/**
 * Entry-point notifiche.
 * Al momento inizializza solo i toast per essere ri-usati da altri moduli
 * (WS handler, AI-News, ecc.).
 */
export function initNotifications() {
  initToasts();
}

// esegui subito: il layout importerà solo questo file
initNotifications();

console.log("[Notifications] Modulo principale inizializzato."); 