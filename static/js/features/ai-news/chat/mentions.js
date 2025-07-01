/* Parsing & highlight delle menzioni @Nome(id)              */
/* Esporta due utility:                                      */
/*   - parseMentions(text)  ->  { cleanText, mentions[] }    */
/*   - highlight(text, me?) ->  html con <span class="mention"> */

const MENTION_RE = /@\[(.+?)\]\(([\da-f]{24})\)/g;

/** Estrae le menzioni e restituisce testo "pulito". */
export function parseMentions(raw) {
  const mentions = [];
  const cleanText = raw.replace(MENTION_RE, (_, name, id) => {
    mentions.push({ id, name });
    return `@${name}`;
  });
  return { cleanText, mentions };
}

/** Converte le menzioni in <a/>, evidenziando quelle che riguardano l'utente corrente. */
export function highlight(text, currentUserId = null) {
  return text.replace(MENTION_RE, (_, name, id) => {
    const cls = ['mention'];
    if (id === currentUserId) cls.push('mention-highlight');
    return `<a href="#" class="${cls.join(' ')}" data-id="${id}">@${name}</a>`;
  });
} 