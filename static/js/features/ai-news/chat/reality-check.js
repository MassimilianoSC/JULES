/* ---------------------------------------------------------------
 * reality-check.js  – rimuove commenti "fantasma" in UI
 * ------------------------------------------------------------- */
import { eventBus } from '/static/js/core/event-bus.js'; // Corrected import name
import { buildCommentElement } from './dom-renderer.js'; // Corrected import: buildCommentElement
import chatState from './chat-state.js'; // To get current user info for buildCommentElement

/**
 * Sincronizza la lista commenti con lo stato del DB.
 * - newsId  → id della news AI
 * - container → elemento (e.g. #comments-list-newsId) che contiene i singoli elementi commento.
 */
export async function syncComments(newsId, container) {
  if (!container) {
    console.error(`[RealityCheck] Container non fornito per newsId: ${newsId}`);
    return;
  }
  try {
    // Fetch only top-level comments for the main list sync. Replies are handled separately or within comment items.
    const res = await fetch(`/api/ai-news/${newsId}/comments?page=1&page_size=100`, { // Fetch a large page size for sync
      credentials: 'include'
    });
    if (!res.ok) throw new Error(await res.text());

    const serverData = await res.json(); // Expects { items: [] }
    const serverComments = serverData.items || [];

    /* --- build Set di id lato server + dom --------------------- */
    const idsServer = new Set(serverComments.map(c => c._id));
    // Query for direct children of the container that are comment items.
    // Assuming comment items have a specific ID format or a common class.
    // buildCommentElement creates elements with id `comment-${commentId}`.
    const domNodes  = Array.from(container.querySelectorAll(`[id^="comment-"]`));

    /* a) rimuovi nodi che non esistono più lato server (o non sono più top-level) */
    domNodes.forEach(node => {
      const nodeId = node.id.replace('comment-', ''); // Extract ID
      if (!idsServer.has(nodeId)) {
        // Before removing, ensure it's a direct child meant to be synced here (e.g. not a reply within a comment)
        // This basic sync assumes container holds only top-level comments rendered by this function.
        if (node.parentElement === container) {
            node.remove();
        }
      }
    });

    /* b) aggiungi quelli mancanti o aggiorna esistenti (più complesso, per ora solo aggiungi) */
    const currentUserId = chatState.state.user ? chatState.state.user._id : null;
    const currentUserRole = chatState.state.user ? chatState.state.user.role : null;

    const currentDomIds = new Set(
      Array.from(container.querySelectorAll(`[id^="comment-"]`)).map(n => n.id.replace('comment-', ''))
    );

    serverComments.forEach(c => {
      if (!currentDomIds.has(c._id)) {
        // Ensure newsId is passed to buildCommentElement if it needs it for data attributes
        const commentElement = buildCommentElement(c, newsId, currentUserId, currentUserRole);
        container.appendChild(commentElement);
      }
      // TODO: Implement update logic for existing comments if content/likes changed,
      // or rely on WebSocket events for granular updates.
    });

    console.log('[AI_NEWS_CHAT] reality‑check sync OK for newsId:', newsId);
  } catch (err) {
    console.error('[AI_NEWS_CHAT] reality‑check sync failed for newsId:', newsId, err);
  }
}

/* ---------------------------------------------------------------
 * auto‑bootstrap  (eseguito quando la chat viene inizializzata)
 * ------------------------------------------------------------- */
eventBus.on('chat:init', ({ newsId }) => {
  // Target the specific list where comments are rendered.
  const commentsListContainer = document.getElementById(`comments-list-${newsId}`);
  if (commentsListContainer) {
    console.log(`[RealityCheck] chat:init received for ${newsId}, syncing comments.`);
    syncComments(newsId, commentsListContainer);
  } else {
    console.warn(`[RealityCheck] chat:init for ${newsId}, but #comments-list-${newsId} not found.`);
  }
}); 