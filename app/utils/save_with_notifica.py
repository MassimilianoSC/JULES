# ATTENZIONE: Questa funzione è deprecata e non dovrebbe più essere usata.
# La logica di notifica e conferma è ora gestita direttamente
# nei controller delle risorse (es. links.py, documents.py) utilizzando
# gli helper in notification_helpers.py.

async def save_and_notify(*args, **kwargs):
    """
    Questa funzione è un guscio vuoto per mantenere la compatibilità
    durante il refactoring. Verrà rimossa a breve.
    """
    print("[DEPRECATED] La funzione save_and_notify è stata chiamata ma è obsoleta. Ignorata.")
    pass
