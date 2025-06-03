from datetime import datetime
from fastapi import Request
from app.notifiche import crea_notifica


async def save_and_notify(
    *,
    request:   Request,
    collection: str,
    payload:    dict,
    tipo:       str,
    titolo:     str,
    branch:     str,
):
    """
    Inserisce `payload` in `collection` e genera la notifica.
    Ritorna l'`inserted_id` del documento creato.
    """
    db  = request.app.state.db
    res = await db[collection].insert_one(
        {**payload, "created_at": datetime.utcnow()}
    )

    await crea_notifica(
        request=request,
        tipo=tipo,
        titolo=titolo,
        branch=branch,
        id_risorsa=str(res.inserted_id),
        employment_type=payload.get("employment_type", ["*"])
    )
    return res.inserted_id
