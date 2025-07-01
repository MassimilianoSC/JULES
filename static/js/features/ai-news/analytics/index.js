/* ------------------------------------------------------------------
 *  analytics/index.js – orchestration layer (views + likes + share)
 * -----------------------------------------------------------------*/
import { trackView, toggleViews } from './views.js';
import { likeNews, shareNews }   from './likes.js';
import { bus } from '/static/js/core/event-bus.js';

/* auto‑track view on page load ----------------------------------- */
const newsIdInBody = document.body.dataset.newsId;
if (newsIdInBody) trackView(newsIdInBody, 'page-load');

/* delega click (like / share / toggle views) --------------------- */
document.addEventListener('click', e => {
  /* like */
  const likeBtn = e.target.closest('.like-btn');
  if (likeBtn) {
    return likeNews(likeBtn.dataset.news, likeBtn.dataset.comment, likeBtn);
  }

  /* share */
  const shareBtn = e.target.closest('.share-btn');
  if (shareBtn) {
    return shareNews(shareBtn.dataset.news);
  }

  /* toggle views */
  const viewsBtn = e.target.closest('.views-btn');
  if (viewsBtn) {
    return toggleViews(viewsBtn.dataset.news);
  }
});

/* log quando arrivano eventi dal WS (debug) ---------------------- */
bus.on('ws:ai-news', p => {
  if (p?.type === 'view/update') console.log('[WS] views update', p);
  if (p?.type === 'like/update') console.log('[WS] like update',  p);
}); 