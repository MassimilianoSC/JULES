// Wrapper Toastify per notifiche globali
import Toastify from "https://cdn.jsdelivr.net/npm/toastify-js@1.12.0/src/toastify-es.js";

let theme = {
  duration: 5000,
  close: true,
  gravity: "top",
  position: "right",
  offset: { y: 48 },
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
 * @param {'info'|'success'|'error'} [p.type='info']
 */
export function showToast({ title, body, type = "info" }) {
  const bg = {
    info:    "linear-gradient(135deg,#3b82f6,#06b6d4)",
    success: "linear-gradient(135deg,#22c55e,#16a34a)",
    error:   "linear-gradient(135deg,#ef4444,#b91c1c)",
  }[type] ?? theme.background;

  Toastify({
    ...theme,
    text: `<strong>${title}</strong><br>${body}`,
    className: "shadow-lg rounded-lg text-sm",
    style: { background: bg },
    stopOnFocus: true,
  }).showToast();
} 