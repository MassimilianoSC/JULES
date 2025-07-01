/* ------------------------------------------------------------------
 *  likes.js – like & share AI‑News
 * -----------------------------------------------------------------*/
import { bus } from '/static/js/core/event-bus.js';

export async function likeNews(newsId, commentId = null, btn = null) {
  if (!newsId) return;
  if (!commentId) console.warn('[likeNews] commentId mancante (like su news?)');

  const url = commentId
    ? `/ai-news/${newsId}/like/${commentId}`
    : `/api/ai-news/${newsId}/like`;

  console.log('[DEBUG_AI_NEWS] likeNews ↑', url);

  try {
    const res = await fetch(url, { method: 'POST', credentials: 'include' });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    /* aggiorna contatore se il template lo espone */
    if (btn && data.likes !== undefined) {
      const span = btn.querySelector('.like-count');
      if (span) span.textContent = data.likes;
    }

    bus.emit('ai:like:local', { newsId, commentId, likes: data.likes });
  } catch (err) {
    console.error('[DEBUG_AI_NEWS] Errore likeNews:', err);
  }
}

/* --------------------------------------------------------------- */
export async function shareNews(newsId) {
  if (!newsId) return;
  const url = `${location.origin}/ai-news/${newsId}`;

  try {
    if (navigator.share) {
      await navigator.share({ title: 'AI‑News', url });
    } else {
      await navigator.clipboard.writeText(url);
      alert('Link copiato negli appunti');
    }
    bus.emit('ai:share:local', { newsId });
  } catch (err) {
    console.error('[DEBUG_AI_NEWS] shareNews error:', err);
  }
} 