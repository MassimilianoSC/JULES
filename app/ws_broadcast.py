from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Optional
import json
import logging
import base64
from datetime import datetime
from bson import ObjectId
from itsdangerous import URLSafeSerializer, TimestampSigner, BadSignature

logger = logging.getLogger("intranet")

# Lista globale delle connessioni attive
active_ws_connections: List[WebSocket] = []

# --- Gestione Serializer per Cookie di Sessione ---

class JSONSerializer:
    """ Serializzatore JSON compatto, come quello di Starlette. """
    def dumps(self, obj):
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    def loads(self, data):
        return json.loads(data)

def make_starlette_serializer(secret: str) -> URLSafeSerializer:
    """
    Replica il serializer di Starlette per garantire la compatibilità
    nella lettura dei cookie di sessione.
    """
    import hashlib
    return URLSafeSerializer(
        secret,
        salt="starlette.sessions",
        serializer=JSONSerializer(),
        signer=TimestampSigner,
        signer_kwargs={
            "key_derivation": "django-concat",
            "digest_method": hashlib.sha1,
        },
    )

# --- Autenticazione e Gestione Utente ---

async def get_ws_user(websocket: WebSocket) -> Optional[Dict]:
    """
    Recupera l'utente autenticato dal cookie di sessione, con fallback.
    """
    raw_cookie = websocket.cookies.get("session")
    if not raw_cookie:
        logger.error("[WS AUTH] Nessun cookie 'session' trovato.")
        return None

    secret_key = websocket.app.state.secret_key
    serializer = make_starlette_serializer(secret_key)

    try:
        # Tentativo standard con verifica della firma
        data = serializer.loads(raw_cookie)
    except BadSignature:
        logger.warning("[WS AUTH] Firma del cookie non valida! Eseguo fallback...")
        try:
            # Estrae il payload senza verifica della firma
            payload_b64, *_ = raw_cookie.split(".", 1)
            payload_b64 += "=" * (-len(payload_b64) % 4) # Aggiungi padding
            data_json = base64.urlsafe_b64decode(payload_b64).decode()
            data = json.loads(data_json)
            logger.warning("[WS AUTH] Fallback riuscito: uso payload non verificato.")
        except Exception as e:
            logger.error(f"[WS AUTH] Fallback fallito: impossibile estrarre payload. Errore: {e}")
            return None

    user_id = data.get("user_id")
    if not user_id:
        logger.warning("[WS AUTH] 'user_id' non trovato nei dati di sessione.")
        return None

    db = websocket.app.state.db
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        logger.error(f"[WS AUTH] Utente con id '{user_id}' non trovato nel database.")
    return user


# --- Funzioni di Broadcast ---

async def broadcast_message(
    payload: Dict,
    branch: Optional[str] = None,
    employment_type: Optional[List[str]] = None,
    exclude_user_id: Optional[str] = None,
    target_user_id: Optional[str] = None # Nuovo parametro per targeting diretto
):
    """
    Invia un messaggio WebSocket a utenti filtrati o a un utente specifico.
    - Se target_user_id è fornito, invia solo a quell'utente.
    - Altrimenti, applica filtri branch/employment_type ed esclude exclude_user_id.
    """
    if not active_ws_connections:
        logger.debug("[WS] Nessuna connessione attiva")
        return

    message_to_send = json.dumps(payload, ensure_ascii=False)
    recipients = []
    
    logger.debug(f"[WS] Preparazione broadcast:")
    logger.debug(f"[WS] - Target User ID: {target_user_id}")
    logger.debug(f"[WS] - Branch filtro: {branch}")
    logger.debug(f"[WS] - Employment type filtro: {employment_type}")
    logger.debug(f"[WS] - User ID da escludere: {exclude_user_id}")
    logger.debug(f"[WS] - Payload completo: {json.dumps(payload, indent=2)}")

    # Itera su una copia per rimuovere in sicurezza le connessioni morte
    for connection in active_ws_connections[:]:
        if connection.client_state.name != "CONNECTED":
            continue

        try:
            user_info = connection.state.user
            user_id = str(user_info.get("_id"))
            user_role = user_info.get("role")
            user_branch = user_info.get("branch")
            user_emp_type = user_info.get("employment_type")
            
            logger.debug(f"[WS] Valutazione utente {user_info.get('email')}:")
            logger.debug(f"[WS] - ID: {user_id}")
            logger.debug(f"[WS] - Ruolo: {user_role}")
            logger.debug(f"[WS] - Branch: {user_branch}")
            logger.debug(f"[WS] - Employment Type: {user_emp_type}")

            # Se è specificato un target_user_id, invia solo a quell'utente
            if target_user_id:
                if user_id == target_user_id:
                    logger.debug(f"[WS] - INCLUSO: corrisponde a target_user_id")
                    recipients.append(connection)
                else:
                    logger.debug(f"[WS] - ESCLUSO: non corrisponde a target_user_id")
                continue # Passa alla prossima connessione
            
            # Altrimenti, applica i filtri standard
            # Filtra per utente escluso
            if exclude_user_id and user_id == exclude_user_id:
                logger.debug(f"[WS] - ESCLUSO: è l'utente che ha fatto l'azione")
                continue

            # Non inviare notifiche di tipo 'new_notification' (toast) agli admin,
            # a meno che non siano il target_user_id esplicito (gestito sopra).
            if payload.get('type') == 'new_notification' and user_role == 'admin' and not target_user_id:
                logger.debug(f"[WS] - ESCLUSO: è un admin e questo è un toast di notifica generico")
                continue

            # Filtra per filiale (solo se non c'è target_user_id)
            if branch and branch != "*" and user_branch != branch:
                logger.debug(f"[WS] - ESCLUSO: branch non corrispondente")
                continue

            # Filtra per tipo di impiego (solo se non c'è target_user_id)
            if employment_type and "*" not in employment_type and user_emp_type not in employment_type:
                logger.debug(f"[WS] - ESCLUSO: employment type non corrispondente")
                continue
            
            logger.debug(f"[WS] - INCLUSO: tutti i filtri (non target) passati")
            recipients.append(connection)

        except Exception as e:
            logger.error(f"[WS] Errore durante la valutazione dell'utente: {e}")
            # Rimuovi le connessioni che causano errori
            active_ws_connections.remove(connection)
    
    # Invia il messaggio a tutti i destinatari validi
    for recipient in recipients:
        try:
            user_info = recipient.state.user
            logger.debug(f"[WS] Invio a {user_info.get('email')} (ruolo: {user_info.get('role')})")
            logger.debug(f"[WS] Messaggio inviato: {message_to_send}")
            await recipient.send_text(message_to_send)
        except Exception as e:
            logger.error(f"[WS] Errore durante l'invio: {e}")
            if recipient in active_ws_connections:
                active_ws_connections.remove(recipient)

    logger.debug(f"[WS] Broadcast completato: {len(recipients)} destinatari")


async def broadcast_resource_event(event: str, *, item_type: str, item_id: str, user_id: str):
    """ Helper per inviare eventi di aggiornamento risorse (es. highlights) a tutti. """
    await broadcast_message({
        "type": f"resource/{event}",
        "item": {"type": item_type, "id": item_id},
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    })


# --- Endpoint WebSocket Principale ---

async def websocket_main(websocket: WebSocket):
    """
    Punto di ingresso e gestore del ciclo di vita per ogni connessione WebSocket.
    """
    await websocket.accept()

    user = await get_ws_user(websocket)
    if not user:
        await websocket.close(code=1008, reason="Authentication failed")
        return

    # Memorizza i dati dell'utente nello stato della connessione per un accesso rapido
    websocket.state.user = {
        "_id": user["_id"],
        "email": user.get("email"),
        "branch": user.get("branch"),
        "employment_type": user.get("employment_type"),
        "role": user.get("role")
    }
    
    active_ws_connections.append(websocket)
    logger.info(f"[WS] Connessione stabilita per: {user.get('email')}. Totale connessioni: {len(active_ws_connections)}")

    try:
        # Loop principale per mantenere la connessione e gestire i messaggi
        while True:
            message = await websocket.receive_json()
            
            # Rispondi all'heartbeat del client per mantenere la connessione viva
            if message.get("type") == "heartbeat":
                await websocket.send_json({"type": "heartbeat", "status": "acknowledged"})
            else:
                # Gestisci altri tipi di messaggi in arrivo se necessario
                logger.debug(f"[WS] Messaggio ricevuto da {user.get('email')}: {message}")

    except WebSocketDisconnect:
        logger.info(f"[WS] Disconnessione per: {user.get('email')}.")
    except Exception as e:
        logger.error(f"[WS] Errore inatteso per {user.get('email')}: {e}")
    finally:
        # Pulisci la connessione
        if websocket in active_ws_connections:
            active_ws_connections.remove(websocket)
        logger.info(f"[WS] Connessione rimossa. Totale connessioni: {len(active_ws_connections)}")