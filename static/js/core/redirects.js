/**
 * Gestisce i redirect dopo le azioni CRUD
 */

function delayedRedirect(url, delay = 500) {
    console.log(`[Redirects] Redirect a ${url} tra ${delay}ms`);
    setTimeout(() => {
        window.location.href = url;
    }, delay);
}

// Funzione per mostrare i log salvati
function showSavedLogs() {
    const logs = JSON.parse(sessionStorage.getItem('debug_logs') || '[]');
    if (logs.length > 0) {
        console.log('--- Log precedenti al redirect ---');
        logs.forEach(log => console.log(log));
        console.log('--------------------------------');
        sessionStorage.removeItem('debug_logs');
    }
}

// Mostra i log salvati quando la pagina si carica
document.addEventListener('DOMContentLoaded', showSavedLogs);

export function initRedirects() {
    document.body.addEventListener('redirect-to-documents', () => {
        console.log('[Redirects] Ricevuto evento redirect-to-documents');
        delayedRedirect('/documents');
    });

    document.body.addEventListener('redirect-to-links', () => {
        console.log('[Redirects] Ricevuto evento redirect-to-links');
        delayedRedirect('/links');
    });

    document.body.addEventListener('redirect-to-contacts', () => {
        console.log('[Redirects] Ricevuto evento redirect-to-contacts');
        delayedRedirect('/contatti');
    });

    document.body.addEventListener('redirect-to-contatti', () => {
        console.log('[Redirects] Ricevuto evento redirect-to-contatti');
        delayedRedirect('/contatti');
    });

    document.body.addEventListener('redirect-to-news', () => {
        console.log('[Redirects] Ricevuto evento redirect-to-news');
        delayedRedirect('/news');
    });

    document.body.addEventListener('redirect-to-ai-news', () => {
        console.log('[Redirects] Ricevuto evento redirect-to-ai-news');
        delayedRedirect('/ai-news');
    });

    // Log per confermare che gli handler sono stati registrati
    console.log('[Redirects] Handler registrati per:', [
        'redirect-to-documents',
        'redirect-to-links',
        'redirect-to-contacts',
        'redirect-to-contatti',
        'redirect-to-news',
        'redirect-to-ai-news'
    ]);
}

// Inizializza i redirect quando il modulo viene importato
initRedirects();

// Log per confermare che il modulo è stato caricato
console.log('[Redirects] Modulo inizializzato correttamente.'); 