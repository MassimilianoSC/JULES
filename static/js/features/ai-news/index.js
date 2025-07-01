import { eventBus } from "/static/js/core/event-bus.js";
import { showToast } from "/static/js/features/notifications/toast.js";

// Funzione tempo relativo
function timeAgo(date) {
  const seconds = Math.floor((new Date() - new Date(date)) / 1000);
  const intervals = {
    anno: 31536000,
    mese: 2592000,
    settimana: 604800,
    giorno: 86400,
    ora: 3600,
    minuto: 60,
    secondo: 1
  };
  for (let [unit, secondsInUnit] of Object.entries(intervals)) {
    const interval = Math.floor(seconds / secondsInUnit);
    if (interval >= 1) {
      return `${interval} ${unit}${interval > 1 ? 'i' : ''} fa`;
    }
  }
  return 'adesso';
}

// Loading states
function setLoading(newsId, isLoading) {
  const loadingEl = document.querySelector(`#comments-${newsId} .comments-loading`);
  if (loadingEl) {
    if (isLoading) {
      loadingEl.classList.remove('hidden');
    } else {
      loadingEl.classList.add('hidden');
    }
  }
}

// Carica statistiche per una news
function loadStats(newsId) {
  fetch(`/api/ai-news/${newsId}/stats`)
    .then(response => response.json())
    .then(data => {
      const card = document.getElementById(`ai-news-${newsId}`);
      if (!card) return;

      // Gestione views
      const viewsEl = card.querySelector('#views-' + newsId + ' .stats-count');
      if (viewsEl) {
        viewsEl.textContent = data.stats?.views || 0;
      }

      // Gestione commenti
      const commentsEl = card.querySelector('#comments-' + newsId + ' .stats-count');
      if (commentsEl) {
        commentsEl.textContent = data.stats?.comments || 0;
      }

      // Gestione likes
      const likeBtn = card.querySelector('#likes-' + newsId + ' .stats-count');
      if (likeBtn) {
        likeBtn.textContent = data.stats?.likes || 0;
        
        const likeWrapper = card.querySelector('#likes-' + newsId + ' .like-button');
        if (likeWrapper) {
          if (data.user_liked) {
            likeWrapper.classList.add('text-blue-600');
          } else {
            likeWrapper.classList.remove('text-blue-600');
          }
        }
      }

      // Aggiorna contatore interazioni totali
      const totalInteractions = document.getElementById('total-interactions');
      if (totalInteractions) {
        const current = parseInt(totalInteractions.textContent) || 0;
        totalInteractions.textContent = current + (data.stats?.total_interactions || 0);
      }
    })
    .catch(error => {
      console.warn('Errore nel caricamento delle statistiche:', error);
    });
}

// Carica commenti per una news
function loadComments(newsId) {
  setLoading(newsId, true);
  fetch(`/api/ai-news/${newsId}/comments`)
    .then(response => response.json())
    .then(data => {
      const commentsList = document.querySelector(`#comments-${newsId} .comments-list`);
      commentsList.innerHTML = data.items.map(comment => `
        <div class="p-3 bg-gray-50 rounded-lg">
          <div class="flex justify-between items-start">
            <div>
              <span class="font-medium">${comment.author?.name || 'Utente'}</span>
              <p class="mt-1 text-gray-600">${comment.content}</p>
            </div>
            <span class="text-xs text-gray-500">${timeAgo(comment.created_at)}</span>
          </div>
        </div>
      `).join('');
      setLoading(newsId, false);
    }).catch(() => setLoading(newsId, false));
}

// Gestione commenti
function handleComments() {
  // Toggle visualizzazione commenti
  document.querySelectorAll('.comments-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const newsId = btn.dataset.newsId;
      const commentsSection = document.getElementById(`comments-section-${newsId}`);
      if (commentsSection.classList.contains('hidden')) {
        commentsSection.classList.remove('hidden');
        loadComments(newsId);
      } else {
        commentsSection.classList.add('hidden');
      }
    });
  });

  // Form commenti
  document.querySelectorAll('[data-comment-form]').forEach(form => {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const newsId = form.dataset.id;
      const textarea = form.querySelector('textarea[name="content"]');
      const content = textarea.value.trim();
      if (!content) return;

      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;

      fetch(`/api/ai-news/${newsId}/comments`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify({content})
      }).then(() => {
        textarea.value = '';
        loadStats(newsId);
        loadComments(newsId);
        showToast('Commento inviato!');
      }).finally(() => {
        submitBtn.disabled = false;
      });
    });
  });
}

// Gestione eliminazione
function handleDelete() {
  document.querySelectorAll('[data-delete-comment-btn]').forEach(btn => {
    btn.addEventListener('click', () => {
      const commentId = btn.dataset.id;
      if (confirm('Sei sicuro di voler eliminare questo commento?')) {
        fetch(`/api/ai-news/comments/${commentId}`, {
          method: 'DELETE',
          credentials: 'include'
        }).then(() => {
          const comment = document.getElementById(`comment-${commentId}`);
          comment.remove();
          showToast('Commento eliminato!');
        });
      }
    });
  });
}

// Gestione condivisione
function handleShare() {
  document.querySelectorAll('[data-share-btn]').forEach(btn => {
    btn.addEventListener('click', () => {
      const newsId = btn.dataset.id;
      const title = btn.dataset.title;
      const url = `${window.location.origin}/ai-news/${newsId}`;
      
      if (navigator.share) {
        navigator.share({
          title: title,
          url: url
        });
      } else {
        navigator.clipboard.writeText(url).then(() => {
          showToast('Link copiato negli appunti!');
        });
      }
    });
  });
}

// Gestione filtri
function handleFilters() {
  const filter = document.querySelector('[data-category-filter]');
  if (filter) {
    filter.addEventListener('change', () => {
      const category = filter.value;
      document.querySelectorAll('[data-category]').forEach(card => {
        if (!category || card.dataset.category === category) {
          card.classList.remove('hidden');
        } else {
          card.classList.add('hidden');
        }
      });
    });
  }
}

// Inizializzazione
export function initAiNews() {
  handleComments();
  handleDelete();
  handleShare();
  handleFilters();

  // WebSocket events
  eventBus.on("news.commentUpdated", (data) => {
    const newsId = data.newsId;
    loadStats(newsId);
    if (!document.querySelector(`#comments-${newsId}`).classList.contains('hidden')) {
      loadComments(newsId);
    }
  });
}

// Inizializzazione per una singola riga
export function initAiNewsRow(newsId) {
  // Inizializza i commenti per questa riga
  const commentsToggle = document.querySelector(`#comments-${newsId} .comments-toggle`);
  if (commentsToggle) {
    commentsToggle.addEventListener('click', () => {
      const commentsSection = document.getElementById(`comments-section-${newsId}`);
      if (commentsSection.classList.contains('hidden')) {
        commentsSection.classList.remove('hidden');
        loadComments(newsId);
      } else {
        commentsSection.classList.add('hidden');
      }
    });
  }

  // Inizializza il form commenti
  const commentForm = document.querySelector(`#comment-form-${newsId}`);
  if (commentForm) {
    commentForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const textarea = commentForm.querySelector('textarea[name="content"]');
      const content = textarea.value.trim();
      if (!content) return;

      const submitBtn = commentForm.querySelector('button[type="submit"]');
      submitBtn.disabled = true;

      fetch(`/api/ai-news/${newsId}/comments`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify({content})
      }).then(() => {
        textarea.value = '';
        loadStats(newsId);
        loadComments(newsId);
        showToast('Commento inviato!');
      }).finally(() => {
        submitBtn.disabled = false;
      });
    });
  }

  // Inizializza il pulsante elimina
  const deleteBtn = document.querySelector(`#ai-news-${newsId} [data-delete-btn]`);
  if (deleteBtn) {
    deleteBtn.addEventListener('click', () => {
      if (confirm('Sei sicuro di voler eliminare questa news?')) {
        const form = deleteBtn.closest('form');
        form.submit();
      }
    });
  }

  // Inizializza il pulsante condividi
  const shareBtn = document.querySelector(`#ai-news-${newsId} [data-share-btn]`);
  if (shareBtn) {
    shareBtn.addEventListener('click', () => {
      const title = shareBtn.dataset.title;
      const url = `${window.location.origin}/ai-news/${newsId}`;
      
      if (navigator.share) {
        navigator.share({
          title: title,
          url: url
        });
      } else {
        navigator.clipboard.writeText(url).then(() => {
          showToast('Link copiato negli appunti!');
        });
      }
    });
  }

  // Carica le statistiche iniziali
  loadStats(newsId);

  // WebSocket events per questa riga
  eventBus.on("news.commentUpdated", (data) => {
    if (data.newsId === newsId) {
      loadStats(newsId);
      const commentsSection = document.getElementById(`comments-section-${newsId}`);
      if (!commentsSection.classList.contains('hidden')) {
        loadComments(newsId);
      }
    }
  });
} 