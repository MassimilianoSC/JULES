/* ------------------------------------------------------------------
 *  views.js  – tracking visualizzazioni AI‑News
 * -----------------------------------------------------------------*/
import { bus } from '/static/js/core/event-bus.js';

const viewedDocs = new Set();          // debounce locale

/** ▸ invia evento "view" al backend e aggiorna il contatore DOM   */
export async function trackView(newsId, actionType = 'view') {
  if (!newsId) return;

  /* debounce client‑side (es. 2 click download + preview) */
  const k = `${newsId}:${actionType}`;
  if (viewedDocs.has(k)) {
    console.log(`[DEBUG_AI_NEWS] debounced view ${k}`);
    return;
  }

  viewedDocs.add(k);

  console.log(`[DEBUG_AI_NEWS] Tracking view for ${newsId}, type: ${actionType}`);
  try {
    const res = await fetch(`/api/ai-news/${newsId}/view`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ action_type: actionType }),
      credentials: 'include'
    });

    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    console.log('[DEBUG_AI_NEWS] View tracked:', data);

    if (data.success && !data.debounced) {
      updateDomCounter(newsId, data.views ?? data.stats?.views);
      /* broadcast locale per eventuali widget interni */
      bus.emit('ai:view:local', { newsId, views: data.views });
    }
  } catch (err) {
    console.error('[DEBUG_AI_NEWS] Error tracking view:', err);
  }
}

/* ▸ mostra/nasconde la sezione "views‑details" ------------------- */
export function toggleViews(newsId) {
  const el = document.getElementById(`views-${newsId}`);
  if (el) el.classList.toggle('hidden');
}

/* ▸ update contatore inline ------------------------------------- */
function updateDomCounter(newsId, views) {
  const counter = document.querySelector(`#views-${newsId} .stats-count`);
  if (counter && typeof views !== 'undefined') counter.textContent = views;
}

/* ▸ listener automatico preview / download ---------------------- */
function autoTrackClicks() {
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href^="/ai-news/"]');
    if (!a) return;

    const [, , id, maybeAction] = a.getAttribute('href').split('/'); // ['', 'ai-news', id, 'preview'?]
    if (!id) return;

    /* preview */
    if (maybeAction === 'preview') {
      trackView(id, 'preview');
      return;
    }

    /* download (tutto ciò che NON termina con /preview) */
    if (maybeAction && maybeAction !== 'preview') {
      trackView(id, 'download');
    }
  });
}

/* ▸ bootstrap ---------------------------------------------------- */
autoTrackClicks();

/* ▸ bridge bus esterno ------------------------------------------ */
bus.on('ai:view', ({ newsId, type }) => trackView(newsId, type));
bus.on('ai:views:toggle',  toggleViews);

/* ---------- WS realtime --------------------------------------- */
bus.on('ws:ai-news', p => {
  if (p?.type === 'view/update') {
    updateDomCounter(p.news_id, p.views);
  }
}); 