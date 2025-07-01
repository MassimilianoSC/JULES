// Funzione per gestire l'animazione delle card
function handleCardAnimation(card) {
  // Se la card ha già l'animazione in corso, non fare nulla
  if (card.classList.contains('play-animation')) {
    return;
  }
  
  // Aggiungi la classe per far partire l'animazione
  card.classList.add('play-animation');
  
  // Rimuovi la classe dopo che l'animazione è finita
  card.addEventListener('animationend', () => {
    card.classList.remove('animate-fadein', 'play-animation');
  }, { once: true });
}

// Osserva le modifiche al DOM per intercettare nuove card
const observer = new MutationObserver((mutations) => {
  mutations.forEach((mutation) => {
    if (mutation.type === 'childList') {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) { // Element node
          // Cerca le card animate nel nodo aggiunto
          const cards = node.querySelectorAll('.animate-fadein');
          cards.forEach(handleCardAnimation);
          
          // Controlla se il nodo stesso è una card animata
          if (node.classList?.contains('animate-fadein')) {
            handleCardAnimation(node);
          }
        }
      });
    }
  });
});

// Inizia a osservare il documento
document.addEventListener('DOMContentLoaded', () => {
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
  
  // Gestisci le card già presenti nel DOM
  document.querySelectorAll('.animate-fadein').forEach(handleCardAnimation);
}); 