import { eventBus } from '../../core/event-bus.js';

// Aggiorna il ticker quando arriva una nuova news
eventBus.on('news.updated', () => {
    htmx.trigger('#news-ticker', 'refreshNewsEvent');
});

// Gestione dello scroller orizzontale per le news
document.addEventListener('DOMContentLoaded', () => {
    const scroller = document.getElementById('news-scroller');
    const leftBtn = document.getElementById('scroll-left-btn');
    const rightBtn = document.getElementById('scroll-right-btn');

    if (!scroller || !leftBtn || !rightBtn) return;

    // Configurazione dello scroll
    const SCROLL_AMOUNT = 400; // px da scrollare per click
    const SCROLL_BEHAVIOR = { behavior: 'smooth' };

    // Funzioni di scroll
    const scrollLeft = () => {
        scroller.scrollBy({ left: -SCROLL_AMOUNT, ...SCROLL_BEHAVIOR });
    };

    const scrollRight = () => {
        scroller.scrollBy({ left: SCROLL_AMOUNT, ...SCROLL_BEHAVIOR });
    };

    // Event listeners per i pulsanti
    leftBtn.addEventListener('click', scrollLeft);
    rightBtn.addEventListener('click', scrollRight);

    // Gestione visibilità pulsanti in base alla posizione dello scroll
    const updateButtonVisibility = () => {
        const isAtStart = scroller.scrollLeft <= 0;
        const isAtEnd = scroller.scrollLeft >= (scroller.scrollWidth - scroller.clientWidth);

        // Aggiorna opacità invece di display per mantenere l'animazione
        leftBtn.style.opacity = isAtStart ? '0' : '1';
        rightBtn.style.opacity = isAtEnd ? '0' : '1';

        // Disabilita i pulsanti quando non necessari
        leftBtn.disabled = isAtStart;
        rightBtn.disabled = isAtEnd;
    };

    // Osserva cambiamenti nel contenuto per aggiornare i pulsanti
    const observer = new ResizeObserver(updateButtonVisibility);
    observer.observe(scroller);

    // Event listeners per aggiornare i pulsanti
    scroller.addEventListener('scroll', updateButtonVisibility);
    window.addEventListener('resize', updateButtonVisibility);

    // Inizializza lo stato dei pulsanti
    updateButtonVisibility();

    // Gestione scroll con tastiera (accessibilità)
    scroller.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            scrollLeft();
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            scrollRight();
        }
    });
}); 