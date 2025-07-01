export class EmojiPicker {
    constructor(button, textarea) {
        this.button = button;
        this.textarea = textarea;
        this.picker = null;
        this.emojiData = null;
        this.currentCategory = 'smileys';

        this.loadEmojiData();
        this.button.addEventListener('click', () => this.togglePicker());
    }

    async loadEmojiData() {
        try {
            const response = await fetch('/static/js/features/ai-news/emoji-data.json');
            this.emojiData = await response.json();
            this.createPicker();
        } catch (error) {
            console.error('Errore nel caricamento degli emoji:', error);
        }
    }

    createPicker() {
        this.picker = document.createElement('div');
        this.picker.className = 'emoji-picker hidden';
        
        // Crea l'header con le categorie
        const header = document.createElement('div');
        header.className = 'emoji-picker-header';
        
        // Aggiungi le categorie
        Object.keys(this.emojiData).forEach(category => {
            const categoryButton = document.createElement('div');
            categoryButton.className = 'emoji-picker-category';
            categoryButton.innerHTML = this.getCategoryIcon(category);
            categoryButton.addEventListener('click', () => this.switchCategory(category));
            header.appendChild(categoryButton);
        });
        
        // Crea il contenuto
        const content = document.createElement('div');
        content.className = 'emoji-picker-content';
        
        this.picker.appendChild(header);
        this.picker.appendChild(content);
        
        // Posiziona il picker
        this.button.parentNode.appendChild(this.picker);
        
        // Gestisci click fuori dal picker
        document.addEventListener('click', this.handleOutsideClick.bind(this));
        
        // Mostra la categoria iniziale
        this.switchCategory(this.currentCategory);
    }

    getCategoryIcon(category) {
        const icons = {
            'smileys': '😊',
            'people': '👥',
            'animals': '🐶',
            'food': '🍔',
            'activities': '⚽',
            'travel': '✈️',
            'objects': '💡',
            'symbols': '❤️',
            'flags': '🏁'
        };
        return icons[category] || '😊';
    }

    switchCategory(category) {
        if (!this.picker || !this.emojiData) return;
        
        this.currentCategory = category;
        
        // Aggiorna lo stato attivo delle categorie
        const categories = this.picker.querySelectorAll('.emoji-picker-category');
        categories.forEach(cat => cat.classList.remove('active'));
        categories[Object.keys(this.emojiData).indexOf(category)].classList.add('active');
        
        // Aggiorna il contenuto
        const content = this.picker.querySelector('.emoji-picker-content');
        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'emoji-category';
        
        this.emojiData[category].forEach(emoji => {
            const emojiSpan = document.createElement('span');
            emojiSpan.className = 'emoji-item';
            emojiSpan.textContent = emoji;
            emojiSpan.addEventListener('click', () => this.insertEmoji(emoji));
            categoryDiv.appendChild(emojiSpan);
        });
        
        content.innerHTML = '';
        content.appendChild(categoryDiv);
    }

    insertEmoji(emoji) {
        const start = this.textarea.selectionStart;
        const end = this.textarea.selectionEnd;
        const text = this.textarea.value;
        
        this.textarea.value = text.substring(0, start) + emoji + text.substring(end);
        this.textarea.selectionStart = this.textarea.selectionEnd = start + emoji.length;
        this.textarea.focus();
        
        this.togglePicker();
    }

    togglePicker() {
        if (!this.picker) return;
        this.picker.classList.toggle('hidden');
    }

    handleOutsideClick(e) {
        if (!this.picker) return;
        if (!this.picker.contains(e.target) && e.target !== this.button) {
            this.picker.classList.add('hidden');
        }
    }

    destroy() {
        if (this.picker) {
            this.picker.remove();
            document.removeEventListener('click', this.handleOutsideClick.bind(this));
        }
    }
}

// Bridge di compatibilità - da rimuovere gradualmente
window.initEmojiPicker = (button, textarea) => new EmojiPicker(button, textarea); 