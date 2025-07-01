import { eventBus } from '/static/js/core/event-bus.js';
import { moveCardToPinned, moveCardToOriginal, applyPinnedStyle } from './index.js';

function findPinButton(type, id) {
  console.log('[findPinButton] Looking for button:', { type, id });
  const btn = document.querySelector(`.pin-btn[data-item-type="${type}"][data-item-id="${id}"]`);
  console.log('[findPinButton] Found button:', btn);
  return btn;
}

export function handlePinAdd({ type, id }) {
  console.log('[handlePinAdd] Starting...', { type, id });
  const btn = findPinButton(type, id);
  if (!btn) {
    console.warn('[handlePinAdd] Button not found!');
    return;
  }

  const card = btn.parentElement;
  console.log('[handlePinAdd] Found card:', card);
  if (!card || !card.matches('[data-item-type]')) {
    console.warn('[handlePinAdd] Valid card not found!');
    return;
  }

  console.log('[handlePinAdd] Moving card and updating style...');
  moveCardToPinned(card);
  applyPinnedStyle(btn, true);
  console.log('[handlePinAdd] Operation completed!');
}

export function handlePinRemove({ type, id }) {
  console.log('[handlePinRemove] Starting...', { type, id });
  const btn = findPinButton(type, id);
  if (!btn) {
    console.warn('[handlePinRemove] Button not found!');
    return;
  }

  const card = btn.parentElement;
  console.log('[handlePinRemove] Found card:', card);
  if (!card || !card.matches('[data-item-type]')) {
    console.warn('[handlePinRemove] Valid card not found!');
    return;
  }

  console.log('[handlePinRemove] Moving card and updating style...');
  moveCardToOriginal(card);
  applyPinnedStyle(btn, false);
  console.log('[handlePinRemove] Operation completed!');
}

eventBus.on('pin/add', p => {
  console.log('[EventBus pin/add] Received event:', p);
  const btn = findPinButton(p.item_type, p.item_id);
  const card = btn?.parentElement;
  console.log('[EventBus pin/add] Found elements:', { btn, card });
  if (card && card.matches('[data-item-type]')) { 
    moveCardToPinned(card); 
    applyPinnedStyle(btn, true);
    console.log('[EventBus pin/add] Operation completed!');
  } else {
    console.warn('[EventBus pin/add] Valid card not found!');
  }
});

eventBus.on('pin/remove', p => {
  console.log('[EventBus pin/remove] Received event:', p);
  const btn = findPinButton(p.item_type, p.item_id);
  const card = btn?.parentElement;
  console.log('[EventBus pin/remove] Found elements:', { btn, card });
  if (card && card.matches('[data-item-type]')) { 
    moveCardToOriginal(card); 
    applyPinnedStyle(btn, false);
    console.log('[EventBus pin/remove] Operation completed!');
  } else {
    console.warn('[EventBus pin/remove] Valid card not found!');
  }
}); 