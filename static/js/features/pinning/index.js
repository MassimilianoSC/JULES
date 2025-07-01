// -- helper ---------------------------------------------------------
const pinEndpoint = (type, id, pinned) => {
  console.log('[pinEndpoint]', { type, id, pinned });
  return pinned ? `/api/me/pins/${type}/${id}` : `/api/me/pins`;
}

export function applyPinnedStyle(btn, isPinned) {
  console.log('[applyPinnedStyle]', { btn, isPinned });
  if (!btn) {
    console.warn('[applyPinnedStyle] Button not found!');
    return;
  }
  const pinColor = btn.dataset.pinColor || 'text-yellow-400';
  console.log('[applyPinnedStyle] Using color:', pinColor);
  btn.classList.toggle('pinned', isPinned);
  btn.classList.toggle(pinColor, isPinned);
  btn.classList.toggle('text-slate-400', !isPinned);
  btn.textContent = isPinned ? '★' : '☆';
}

// ---------- helpers ----------
function getPinnedSection() {
  console.log('[getPinnedSection] Searching for pinned section...');
  const section = document.querySelector('#highlights-container')
      || document.querySelector('#pinned-cards')
      || document.querySelector('#pinned-grid');
  console.log('[getPinnedSection] Found section:', section);
  return section;
}

function getOriginContainer(card) {
  console.log('[getOriginContainer] Starting...', { card });
  if (!card) {
    console.warn('[getOriginContainer] No card provided!');
    return null;
  }
  const type = card.dataset.itemType;
  console.log('[getOriginContainer] Card type:', type);
  
  const containers = {
    'link': '#links-section',
    'document': '#documents-section',
    'ai_news': '#ai-news-section',
    'contact': '#contacts-section'
  };
  
  const container = document.querySelector(containers[type]);
  console.log('[getOriginContainer] Found container:', container, 'for type:', type);
  return container;
}

// ---------- sposta nella sezione pinnata ----------
export function moveCardToPinned(card) {
  console.log('[moveCardToPinned] Starting...', { card });
  const grid = getPinnedSection();
  console.log('[moveCardToPinned] Grid found:', grid);
  
  if (grid && card) {
    console.log('[moveCardToPinned] Checking if card is already in grid...');
    if (!grid.contains(card)) {
      console.log('[moveCardToPinned] Moving card to grid...');
      // Salva il colore originale se non è già salvato
      if (!card.dataset.originalColor) {
        const bgClass = Array.from(card.classList).find(c => c.startsWith('bg-') && c.endsWith('-50'));
        const borderClass = Array.from(card.classList).find(c => c.startsWith('border-') && c.endsWith('-400'));
        if (bgClass && borderClass) {
          card.dataset.originalColor = bgClass;
          card.dataset.originalBorder = borderClass;
        }
      }
      
      // Rimuovi le classi di colore originali
      if (card.dataset.originalColor) {
        card.classList.remove(card.dataset.originalColor);
        card.classList.remove(card.dataset.originalBorder);
      }
      
      // Aggiungi le classi rosa
      card.classList.add('bg-pink-50');
      card.classList.add('border-pink-400');
      
      grid.prepend(card);
      console.log('[moveCardToPinned] Card moved successfully!');
    } else {
      console.log('[moveCardToPinned] Card is already in grid');
    }
  } else {
    console.warn('[moveCardToPinned] Missing grid or card!', { grid, card });
  }
}

// ---------- rimuovi dalla sezione pinnata ----------
export function moveCardToOriginal(card) {
  console.log('[moveCardToOriginal] Starting...', { card });
  const origin = getOriginContainer(card);
  console.log('[moveCardToOriginal] Origin found:', origin);
  
  if (origin && card) {
    console.log('[moveCardToOriginal] Checking if card is already in origin...');
    if (!origin.contains(card)) {
      console.log('[moveCardToOriginal] Moving card to origin...');
      
      // Rimuovi le classi rosa
      card.classList.remove('bg-pink-50');
      card.classList.remove('border-pink-400');
      
      // Ripristina il colore originale
      if (card.dataset.originalColor) {
        card.classList.add(card.dataset.originalColor);
        card.classList.add(card.dataset.originalBorder);
      }
      
      origin.prepend(card);
      console.log('[moveCardToOriginal] Card moved successfully!');
    } else {
      console.log('[moveCardToOriginal] Card is already in origin');
    }
  } else {
    console.warn('[moveCardToOriginal] Missing origin or card!', { origin, card });
  }
}

// -- restore al page-load ------------------------------------------
export function restorePinnedOrder() {
  console.log('[restorePinnedOrder] Starting...');
  const pinned = JSON.parse(document.body.dataset.pinnedItems || '[]');
  console.log('[restorePinnedOrder] Pinned items:', pinned);

  pinned.forEach(({ type, id }) => {
    console.log('[restorePinnedOrder] Processing item:', { type, id });
    const card = document.querySelector(
      `[data-item-type="${type}"][data-item-id="${id}"]`);
    console.log('[restorePinnedOrder] Found card:', card);
    
    if (card) {
      moveCardToPinned(card);
      getPinnedSection().prepend(card);
      const btn = card.querySelector('.pin-btn');
      if (btn) applyPinnedStyle(btn, true);
      console.log('[restorePinnedOrder] Card restored successfully!');
    } else {
      console.warn('[restorePinnedOrder] Card not found for:', { type, id });
    }
  });
}

// Inizializzazione: ripristina ordine pin e sposta le card già pinnate
document.addEventListener("DOMContentLoaded", () => {
  console.log('[DOMContentLoaded] Initializing pinning system...');
  restorePinnedOrder();
  
  // Aggiungiamo l'event listener globale per i bottoni di pin
  document.addEventListener('click', e => {
    const btn = e.target.closest('.pin-btn');
    if (!btn) return;
    
    const type = btn.dataset.itemType;
    const id = btn.dataset.itemId;
    
    if (type && id) {
      togglePin(type, id, btn);
    }
  });
  
  console.log('[DOMContentLoaded] Pinning system initialized!');
});

// funzione di utilità
function findCard(btn) {
  console.log('[findCard] Looking for card from button:', btn);
  const card = btn.closest('[data-item-type]');
  console.log('[findCard] Found card:', card);
  return card;
}

// -----------------------------------------------------------------
export async function togglePin(type, id, btn) {
  console.log('[togglePin] Starting...', { type, id, btn });
  
  if (!id?.trim()) {
    console.warn('[togglePin] ID missing, aborting');
    return;
  }

  // Trova il div della card (escludendo il bottone)
  const card = btn.parentElement;
  console.log('[togglePin] Found card:', card);
  
  if (!card || !card.matches('[data-item-type]')) {
    console.warn('[togglePin] Valid card not found, aborting');
    return;
  }

  const currentlyPinned = btn.classList.contains("pinned");
  console.log('[togglePin] Current pin state:', currentlyPinned);
  const method = currentlyPinned ? "DELETE" : "POST";

  console.log('[togglePin] Making API call...', { method });
  const res = await fetch(pinEndpoint(type, id, currentlyPinned), {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, id })
  });

  if (!res.ok) {
    console.error('[togglePin] API error:', res.status);
    throw new Error('Pin server error ' + res.status);
  }
  console.log('[togglePin] API call successful!');

  const willBePinned = !currentlyPinned;
  console.log('[togglePin] Updating UI for new state:', willBePinned);
  
  // Prima aggiorniamo lo stile della stella per riflettere il nuovo stato
  applyPinnedStyle(btn, willBePinned);
  
  // Poi spostiamo la card in base al nuovo stato
  if (willBePinned) {
    moveCardToPinned(card);
  } else {
    moveCardToOriginal(card);
  }
  console.log('[togglePin] Operation completed successfully!');
}

// esposizione globale per i template legacy
window.togglePin = togglePin;