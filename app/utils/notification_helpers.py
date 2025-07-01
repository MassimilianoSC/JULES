# app/utils/notification_helpers.py

import json
from fastapi import Response
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Literal

# --- Tipi e Costanti Centralizzate ---

# Eccezione custom per una gestione degli errori più specifica
class InvalidActionError(ValueError):
    """Raised when an invalid action type is passed to a helper function."""
    pass

# Tipo per le azioni CRUD, per type-safety e auto-completamento
ActionType = Literal['create', 'update', 'delete']

# Livelli di notifica, definiti in un unico posto per coerenza
NOTIFICATION_LEVELS: Dict[ActionType, str] = {
    'create': 'success',
    'update': 'info',
    'delete': 'warning'
}

# Testi per i toast dei destinatari (via WebSocket)
RECIPIENT_TITLES: Dict[ActionType, str] = {
    'create': "Nuova Risorsa: {resource}",
    'update': "Risorsa Aggiornata: {resource}",
    'delete': "Risorsa Rimossa: {resource}"
}
RECIPIENT_BODIES: Dict[ActionType, str] = {
    'create': "È stata aggiunta la risorsa «{name}».",
    'update': "La risorsa «{name}» è stata modificata.",
    'delete': "La risorsa «{name}» è stata eliminata."
}

# Testi per le conferme dell'admin (via HX-Trigger)
ADMIN_TITLES: Dict[ActionType, str] = {
    'create': "Creazione Completata",
    'update': "Modifica Salvata",
    'delete': "Eliminazione Eseguita"
}
ADMIN_MESSAGES: Dict[ActionType, str] = {
    'create': "La risorsa «{name}» è stata creata con successo.",
    'update': "Le modifiche a «{name}» sono state salvate.",
    'delete': "«{name}» è stato eliminato correttamente."
}

# --- Funzioni Helper ---

def create_action_notification_payload(
    action: ActionType,
    resource: str,
    resource_name: str,
    source_user_id: str
) -> Dict[str, Any]:
    """Crea un payload standardizzato per i toast WebSocket destinati agli utenti."""
    print(f"[DEBUG] Creazione payload notifica:")
    print(f"[DEBUG] - Action: {action}")
    print(f"[DEBUG] - Resource: {resource}")
    print(f"[DEBUG] - Resource name: {resource_name}")
    print(f"[DEBUG] - Source user ID: {source_user_id}")

    if action not in NOTIFICATION_LEVELS:
        raise InvalidActionError(f"Azione non valida fornita: {action}")
    
    title = RECIPIENT_TITLES[action].format(resource=resource.capitalize())
    body = RECIPIENT_BODIES[action].format(name=resource_name)
    
    payload = {
        'type': 'new_notification',
        'data': {
            'action': action,
            'resource': resource,
            'title': title,
            'body': body,
            'level': NOTIFICATION_LEVELS[action],
            'source_user_id': source_user_id
        }
    }
    print(f"[DEBUG] Payload generato: {payload}")
    return payload

def create_admin_confirmation_trigger(
    action: ActionType,
    resource_name: str
) -> str:
    """
    Crea l'header HX-Trigger per la conferma dell'admin.
    
    Il payload include:
    - level: per l'icona ('success', 'info', 'warning')
    - duration: durata in ms del popup
    - delay: ritardo in ms per la chiusura della modale
    
    Example:
        trigger = create_admin_confirmation_trigger('create', 'Documento X')
        response.headers['HX-Trigger'] = trigger
    """
    if action not in ADMIN_TITLES:
        raise InvalidActionError(f"Azione non valida fornita: {action}")
    
    trigger_payload = {
        "showAdminConfirmation": {
            "title": ADMIN_TITLES[action],
            "message": ADMIN_MESSAGES[action].format(name=resource_name),
            "level": NOTIFICATION_LEVELS[action],
            "duration": 3000
        },
        "closeModal": {
            "delay": 500
        }
    }
    return json.dumps(trigger_payload)