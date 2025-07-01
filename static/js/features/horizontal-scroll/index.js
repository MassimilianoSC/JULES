/**
 * Componente JavaScript per la gestione di scroller orizzontali.
 * Aggiunge interattività ai pulsanti di navigazione e gestisce
 * la loro visibilità in base alla posizione dello scroll.
 */
function initializeScroller(containerId) {
    const container = document.getElementById(containerId);
    if (!container) {
        // Se il contenitore non esiste in questa pagina, non fare nulla.
        return;
    }

    const scroller = container.querySelector('#news-scroller');
    const scrollLeftBtn = container.querySelector('#scroll-left-btn');
    const scrollRightBtn = container.querySelector('#scroll-right-btn');

    if (!scroller || !scrollLeftBtn || !scrollRightBtn) {
        console.warn(`[Scroller] Elementi necessari per lo scroller (scroller o pulsanti) non trovati all'interno di #${containerId}.`);
        return;
    }

    // Funzione per aggiornare la visibilità dei pulsanti
    function updateButtonVisibility() {
        const scrollLeft = scroller.scrollLeft;
        const scrollWidth = scroller.scrollWidth;
        const clientWidth = scroller.clientWidth;

        // Mostra/nascondi il pulsante sinistro
        scrollLeftBtn.classList.toggle('hidden', scrollLeft <= 0);

        // Mostra/nascondi il pulsante destro
        scrollRightBtn.classList.toggle('hidden', scrollLeft >= scrollWidth - clientWidth - 1);
    }

    // Aggiungi event listener ai pulsanti
    scrollLeftBtn.addEventListener('click', () => {
        // Scorre a sinistra di una quantità pari alla larghezza visibile del contenitore
        scroller.scrollBy({ left: -scroller.clientWidth, behavior: 'smooth' });
    });

    scrollRightBtn.addEventListener('click', () => {
        // Scorre a destra
        scroller.scrollBy({ left: scroller.clientWidth, behavior: 'smooth' });
    });

    // Aggiungi un listener all'evento di scroll per aggiornare i pulsanti dinamicamente
    scroller.addEventListener('scroll', updateButtonVisibility);
    
    // Aggiungi un listener al resize della finestra per ricalcolare la visibilità
    window.addEventListener('resize', updateButtonVisibility);

    // Controlla la visibilità dei pulsanti al caricamento iniziale
    updateButtonVisibility();
    
    console.log(`[Scroller] Componente scroller orizzontale inizializzato per #${containerId}.`);
}

// Inizializza lo scroller per le news quando il DOM è pronto.
// Questo approccio ci permette di avere più scroller sulla stessa pagina in futuro.
document.addEventListener('DOMContentLoaded', () => {
    initializeScroller('news-scroller-container');
}); 