/**
 * Modulo per la visualizzazione dei toast.
 * Esporta solo la funzione 'showToast' e non contiene listener.
 */
import Toastify from "https://cdn.jsdelivr.net/npm/toastify-js@1.12.0/src/toastify-es.js";

// Configurazione di default per i toast
let theme = {
  duration: 5000,
  close: true,
  gravity: "top",
  position: "right",
  offset: { y: 48 },
  stopOnFocus: true,
};

export function initToasts(opts = {}) {
  // permetti override tema (es. colori corporate)
  theme = { ...theme, ...opts };
}

/**
 * Mostra un toast.
 * @param {Object}   p
 * @param {String}   p.title   - Titolo breve
 * @param {String}   p.body    - Corpo HTML o testo
 * @param {'info'|'success'|'error'|'warning'} [p.type='info']
 */
export function showToast({ title, body, type = "info" }) {
  const bg = {
    info:    "linear-gradient(135deg,#3b82f6,#06b6d4)", // Blu/Ciano
    success: "linear-gradient(135deg,#22c55e,#16a34a)", // Verde
    error:   "linear-gradient(135deg,#ef4444,#b91c1c)", // Rosso
    warning: "linear-gradient(135deg,#f97316,#ea580c)", // Arancione
  }[type] || "linear-gradient(135deg,#64748b,#475569)"; // Grigio di default

  Toastify({
    ...theme,
    text: `<strong>${title}</strong><br>${body}`,
    className: "shadow-lg rounded-lg text-sm",
    escapeMarkup: false, // Permette l'uso di HTML nel testo
    style: { background: bg },
  }).showToast();
}

/**
 * Aggiungi un listener per eventi globali scatenati da htmx.
 * Permette al backend di mostrare toast tramite header HX-Trigger.
 * es. HX-Trigger: {"showToast": {"title": "OK", "body": "Fatto!"}}
 */
document.body.addEventListener("showToast", function (evt) {
  const { title, body, type } = evt.detail;
  if (title && body) {
    showToast({ title, body, type });
  }
}); 