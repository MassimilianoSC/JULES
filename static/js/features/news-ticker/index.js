import { eventBus } from '../../core/event-bus.js';

document.addEventListener('DOMContentLoaded', () => {
    const tickerContainer = document.getElementById('news-ticker'); // Usiamo l'ID del contenitore principale del ticker
    const itemsContainer = document.getElementById('news-ticker-items-container');

    if (!tickerContainer || !itemsContainer) {
        console.warn('News ticker container or items container not found.');
        return;
    }

    let animationInterval;
    let scrollAmount = 1; // Pixel da scrollare per frame
    const animationSpeed = 20; // Millisecondi per frame (più basso = più veloce)
    let isPaused = false;

    function достаточноСодержимогоДляСкролла() {
        return itemsContainer.scrollWidth > itemsContainer.clientWidth;
    }

    function startScrolling() {
        if (!достаточноСодержимогоДляСкролла()) {
            // console.log("Ticker: Not enough content to scroll.");
            return;
        }
        // console.log("Ticker: Starting scroll");
        clearInterval(animationInterval); // Pulisce intervalli precedenti
        animationInterval = setInterval(() => {
            if (!isPaused && достаточноСодержимогоДляСкролла()) {
                itemsContainer.scrollLeft += scrollAmount;
                if (itemsContainer.scrollLeft >= (itemsContainer.scrollWidth - itemsContainer.clientWidth -1)) {
                    // Quando si raggiunge la fine, si può clonare il contenuto per un loop infinito
                    // Per ora, semplice reset allo start per evitare overscroll e blocco.
                    // Una soluzione più elegante clonerebbe gli elementi.
                    // itemsContainer.scrollLeft = 0; // Semplice reset

                    // Per un effetto di loop più fluido, potremmo aggiungere il primo elemento alla fine
                    // e quando il primo "originale" scompare, lo si sposta.
                    // Qui un approccio più semplice: quando arriva alla fine, aspetta un po' e ricomincia.
                    // Questo è un placeholder, l'animazione di loop continuo è più complessa.
                    // Temporaneamente, fermiamo lo scroll quando arriva alla fine per evitare comportamenti strani.
                     itemsContainer.scrollLeft = 0; // Torna all'inizio per un loop semplice
                }
            }
        }, animationSpeed);
    }

    function stopScrolling() {
        // console.log("Ticker: Stopping scroll");
        clearInterval(animationInterval);
    }

    // --- Gestione Eventi WebSocket ---
    const createNewsItemElement = (newsData) => {
        const itemSpan = document.createElement('span');
        itemSpan.id = `news-ticker-item-${newsData.id}`;
        itemSpan.className = 'news-ticker-item whitespace-nowrap font-bold';

        const link = document.createElement('a');
        link.href = newsData.url_news; // Usiamo url_news dal payload
        link.className = 'hover:underline hover:text-yellow-200 transition';
        link.textContent = newsData.title;

        itemSpan.appendChild(link);
        return itemSpan;
    };

    const addSeparatorIfNeeded = () => {
        if (itemsContainer.children.length > 0 && itemsContainer.lastChild.nodeName === 'SPAN') {
            const lastChildIsSeparator = itemsContainer.lastChild.classList && itemsContainer.lastChild.classList.contains('news-ticker-separator');
            if (!lastChildIsSeparator) { // Evita doppi separatori
                 // Controlla se l'ultimo figlio NON è già un separatore prima di aggiungerne uno.
                const currentSpans = Array.from(itemsContainer.querySelectorAll('.news-ticker-item'));
                if (currentSpans.length > 1) { // Aggiungi separatore solo se c'è più di un item
                    const prevItem = currentSpans[currentSpans.length-2]; // L'item prima di quello appena aggiunto
                    // Rimuovi eventuale separatore dopo l'item precedente se esiste
                    if(prevItem && prevItem.nextElementSibling && prevItem.nextElementSibling.classList.contains('news-ticker-separator')) {
                        // Non fare nulla, il separatore è già lì o sarà gestito
                    } else {
                        const separator = document.createElement('span');
                        separator.className = 'news-ticker-separator text-cyan-200 font-bold text-lg px-2';
                        separator.innerHTML = '|';
                        itemsContainer.appendChild(separator);
                    }
                }
            }
        }
    };

    const ensureSeparatorsCorrect = () => {
        const items = itemsContainer.querySelectorAll('.news-ticker-item');
        const separators = itemsContainer.querySelectorAll('.news-ticker-separator');
        separators.forEach(sep => sep.remove()); // Rimuovi tutti i separatori esistenti

        items.forEach((item, index) => {
            if (index < items.length - 1) { // Non aggiungere separatore dopo l'ultimo item
                const separator = document.createElement('span');
                separator.className = 'news-ticker-separator text-cyan-200 font-bold text-lg px-2';
                separator.innerHTML = '|';
                item.after(separator); // Inserisci separatore dopo l'item corrente
            }
        });
    };


    eventBus.on("news_ticker_add", (eventData) => {
        // console.log("Received news_ticker_add:", eventData.data);
        const newsItem = createNewsItemElement(eventData.data);
        // Prima di aggiungere il nuovo item, assicuriamoci che ci sia un separatore se necessario
        if (itemsContainer.children.length > 0) { // Se ci sono già items
             if (!itemsContainer.lastElementChild.classList.contains('news-ticker-separator')) {
                const separator = document.createElement('span');
                separator.className = 'news-ticker-separator text-cyan-200 font-bold text-lg px-2';
                separator.innerHTML = '|';
                itemsContainer.appendChild(separator);
            }
        }
        itemsContainer.appendChild(newsItem);
        ensureSeparatorsCorrect();
        stopScrolling();
        startScrolling();
    });

    eventBus.on("news_ticker_update", (eventData) => {
        // console.log("Received news_ticker_update:", eventData.data);
        const newsItemElement = document.getElementById(`news-ticker-item-${eventData.data.id}`);
        if (newsItemElement) {
            const link = newsItemElement.querySelector('a');
            if(link){
                link.href = eventData.data.url_news;
                link.textContent = eventData.data.title;
            }
        }
        // Non è necessario riavviare lo scroll per un update di testo
    });

    eventBus.on("news_ticker_remove", (eventData) => {
        // console.log("Received news_ticker_remove:", eventData.data);
        const newsItemElement = document.getElementById(`news-ticker-item-${eventData.data.id}`);
        if (newsItemElement) {
            const nextSeparator = newsItemElement.nextElementSibling;
            if (nextSeparator && nextSeparator.classList.contains('news-ticker-separator')) {
                nextSeparator.remove();
            } else {
                 // Se l'elemento da rimuovere non è l'ultimo, il separatore da rimuovere potrebbe essere quello prima
                const prevSeparator = newsItemElement.previousElementSibling;
                if (prevSeparator && prevSeparator.classList.contains('news-ticker-separator')) {
                     prevSeparator.remove();
                }
            }
            newsItemElement.remove();
            ensureSeparatorsCorrect();
            stopScrolling();
            startScrolling();
        }
    });

    // --- Gestione Mouse Enter/Leave per Pausa/Ripresa ---
    tickerContainer.addEventListener('mouseenter', () => {
        isPaused = true;
        // console.log("Ticker: Paused by mouseenter");
    });

    tickerContainer.addEventListener('mouseleave', () => {
        isPaused = false;
        // console.log("Ticker: Resumed by mouseleave");
        // Riavvia lo scorrimento solo se era in corso e c'è abbastanza contenuto
        if (animationInterval) { // Se era in corso prima della pausa
             startScrolling(); // Riavvia per assicurare che continui se le condizioni sono soddisfatte
        }
    });

    // Avvia lo scorrimento iniziale
    startScrolling();
    // Aggiorna lo stato dei pulsanti (se li manteniamo o reintroduciamo)
    // updateButtonVisibility(); // Se i pulsanti di scroll manuale fossero ancora usati
}); 