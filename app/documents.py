from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, Response
from app.deps import require_admin, get_current_user, get_docs_coll
from app.utils.save_with_notifica import save_and_notify
from bson import ObjectId
from datetime import datetime
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorCollection
import aiofiles
from mimetypes import guess_type
from app.notifiche import crea_notifica
from fastapi.templating import Jinja2Templates
import sys
import asyncio

# Costante per il percorso base dei documenti
BASE_DOCS_DIR = Path("media/docs")   # cartella radice documenti

def to_str_id(doc: dict) -> dict:
    """Converte l'_id Mongo in stringa per i template Jinja."""
    doc["_id"] = str(doc["_id"])
    return doc

documents_router = APIRouter(tags=["documents"])

@documents_router.post(
    "/documents/upload",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(require_admin)]
)
async def upload_document(
    request: Request,
    title: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    tags: str = Form(None),
    file: UploadFile = File(...),
    show_on_home: str = Form(None)
):
    show_on_home = show_on_home is not None
    # 1. Salva il file fisicamente
    docs_dir = BASE_DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / file.filename
    async with aiofiles.open(dest, "wb") as out:
        await out.write(await file.read())

    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    # 2. Salva il documento in Mongo
    db = request.app.state.db
    doc = {
        "title": title.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list,
        "tags": [tag.strip() for tag in tags.split(",")] if tags else [],
        "filename": file.filename,
        "content_type": file.content_type,
        "uploaded_at": datetime.utcnow()
    }
    result = await db.documents.insert_one(doc)
    doc_id = result.inserted_id

    # 3. Aggiorna home_highlights SOLO ORA
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "document", "object_id": doc_id},
            {"$set": {
                "type": "document",
                "object_id": doc_id,
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "document", "object_id": doc_id})

    # 4. Crea la notifica PRIMA del broadcast
    await crea_notifica(
        request=request,
        tipo="documento",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=str(doc_id),
        employment_type=employment_type_list
    )

    # 5. Invia WebSocket come per link/contatti
    try:
        import json
        from app.ws_broadcast import broadcast_message
        # Recupera la notifica appena creata
        notifica = await db.notifiche.find_one({"id_risorsa": str(doc_id), "tipo": "documento"})
        payload_toast = {
            "type": "new_notification",
            "data": {
                "id": str(notifica["_id"]) if notifica else str(doc_id),
                "message": f"È stato pubblicato un nuovo documento: {notifica.get('titolo', title.strip()) if notifica else title.strip()} ({branch.strip() if branch.strip() != '*' else 'Tutti'})",
                "tipo": "documento"
            }
        }
        await broadcast_message(json.dumps(payload_toast))
        # Aggiorna highlights home (sempre, come per i link)
        payload_highlight = {
            "type": "refresh_home_highlights"
        }
        await broadcast_message(json.dumps(payload_highlight))
    except Exception as e:
        print("[WebSocket] Errore broadcast su creazione documento:", e)

    return RedirectResponse("/documents", status_code=303)

@documents_router.get("/documents/upload", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def show_upload_form(request: Request):
    branches = ["HQE", "HQ ITALIA", "HQIA"]
    types = ["TD", "TI", "AP", "CO"]
    return request.app.state.templates.TemplateResponse(
        "documents/upload.html",
        {"request": request, "branches": branches, "types": types}
    )

@documents_router.get(
    "/documents/{doc_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_document_form(
    request: Request,
    doc_id: str,
    user = Depends(get_current_user),
    docs_coll: AsyncIOMotorCollection = Depends(get_docs_coll)
):
    doc = await docs_coll.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Documento non trovato")
    # Verifica se il documento è in evidenza
    db = request.app.state.db
    highlight = await db.home_highlights.find_one({"type": "document", "object_id": ObjectId(doc_id)})
    doc = to_str_id(doc)
    doc["show_on_home"] = bool(highlight)
    return request.app.state.templates.TemplateResponse(
        "documents/edit_partial.html",
        {"request": request, "d": doc, "user": user}
    )

@documents_router.post(
    "/documents/{doc_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_document_submit(
    request: Request,
    doc_id: str,
    title: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    tags: str = Form(None),
    show_on_home: str = Form(None),
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    await db.documents.update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": {
            "title": title.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "tags": [tag.strip() for tag in tags.split(",")] if tags else []
        }}
    )
    # Gestione home_highlights
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "document", "object_id": ObjectId(doc_id)},
            {"$set": {
                "type": "document",
                "object_id": ObjectId(doc_id),
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "document", "object_id": ObjectId(doc_id)})
    # Elimino tutte le vecchie notifiche relative a questo documento
    await db.notifiche.delete_many({"id_risorsa": str(doc_id), "tipo": "documento"})
    # Dopo l'update, creo una nuova notifica per i nuovi destinatari
    await crea_notifica(
        request=request,
        tipo="documento",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=str(doc_id),
        employment_type=employment_type_list
    )
    updated = await db.documents.find_one({"_id": ObjectId(doc_id)})
    resp = request.app.state.templates.TemplateResponse(
        "documents/row_partial.html",
        {"request": request, "d": updated, "user": current_user}
    )
    resp.headers["HX-Trigger"] = "closeModal"
    # Broadcast WebSocket per aggiornamento real-time dopo modifica
    try:
        import json
        from app.ws_broadcast import broadcast_message
        # Recupera la notifica appena creata/aggiornata
        notifica = await db.notifiche.find_one({"id_risorsa": str(doc_id), "tipo": "documento"})
        payload_update = {
            "type": "update_document",
            "data": {
                "id": str(doc_id),
                "title": title.strip(),
                "branch": branch.strip(),
                "message": f"Documento modificato: {title.strip()} ({branch.strip() if branch.strip() != '*' else 'Tutti'})",
                "tipo": "documento"
            }
        }
        await broadcast_message(json.dumps(payload_update))
        # Aggiorna highlights home (sempre, come per i link)
        payload_highlight = {
            "type": "refresh_home_highlights"
        }
        await broadcast_message(json.dumps(payload_highlight))
    except Exception as e:
        print("[WebSocket] Errore broadcast su update_document:", e)
    return resp

@documents_router.get("/documents/{doc_id}")
async def download_document(doc_id: str, request: Request):
    db = request.app.state.db
    doc = await db.documents.find_one({"_id": doc_id})
    if not doc and ObjectId.is_valid(doc_id):
        doc = await db.documents.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    file_path = BASE_DOCS_DIR / doc["filename"]
    if not file_path.exists():
        raise HTTPException(404, "File non trovato")
    return FileResponse(path=file_path, filename=doc["filename"], media_type=doc.get("content_type", "application/octet-stream"))

@documents_router.get("/documents/{doc_id}/preview")
async def preview_document(doc_id: str, request: Request):
    db = request.app.state.db
    doc = await db.documents.find_one({"_id": doc_id})
    if not doc and ObjectId.is_valid(doc_id):
        doc = await db.documents.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    file_path = BASE_DOCS_DIR / doc["filename"]
    if not file_path.exists():
        raise HTTPException(404, "File non trovato")
    mime, _ = guess_type(str(file_path))
    headers = {"Content-Disposition": f'inline; filename="{doc["filename"]}"'}
    return FileResponse(
        path=file_path,
        filename=doc["filename"],
        media_type=mime or "application/octet-stream",
        headers=headers
    )

@documents_router.get("/documents", response_class=HTMLResponse)
async def list_documents(
    request: Request,
    current_user = Depends(get_current_user),
    docs_coll: AsyncIOMotorCollection = Depends(get_docs_coll)
):
    try:
        employment_type = current_user.get("employment_type")
        branch = current_user.get("branch")
        role = current_user.get("role")

        # Ripristina la logica della versione precedente
        if role == "admin" or not employment_type:
            filter_query = {}
        else:
            filter_query = {
                "$and": [
                    {
                        "$or": [
                            {"branch": "*"},
                            {"branch": branch}
                        ]
                    },
                    {
                        "$or": [
                            {"employment_type": {"$in": [employment_type, "*"]}},
                            {"employment_type": employment_type},
                            {"employment_type": "*"}
                        ]
                    }
                ]
            }

        documents = await docs_coll.find(filter_query).sort("uploaded_at", -1).to_list(None)
        documents = [to_str_id(doc) for doc in documents]
    except Exception as e:
        documents = []

    if request.headers.get("HX-Request") == "true":
        return request.app.state.templates.TemplateResponse(
            "documents/list_partial.html",
            {"request": request, "documents": documents, "current_user": current_user}
        )
    else:
        return request.app.state.templates.TemplateResponse(
            "documents.html",
            {"request": request, "documents": documents, "current_user": current_user}
        )

@documents_router.delete("/documents/{doc_id}")
async def delete_document(request: Request, doc_id: str):
    db = request.app.state.db
    # Recupera info documento prima di eliminare
    doc = await db.documents.find_one({"_id": ObjectId(doc_id)})
    title = doc["title"] if doc else ""
    await db.documents.delete_one({"_id": ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id})
    # rimuovi eventuale highlight
    try:
        obj_id = ObjectId(doc_id)
    except Exception:
        obj_id = doc_id
    await db.home_highlights.delete_many({
        "type": "document",
        "$or": [
            {"object_id": obj_id},
            {"object_id": str(doc_id)}
        ]
    })
    # Invia WebSocket come per link/contatti
    try:
        import json
        from app.ws_broadcast import broadcast_message
        user_id = getattr(getattr(request, 'state', None), 'user', {}).get('_id') if hasattr(request.state, 'user') and request.state.user else None
        payload_remove = {
            "type": "remove_document",
            "data": {
                "id": str(doc_id),
                "user_id": str(user_id) if user_id else None,
                "title": doc["title"] if doc else None,
                "branch": doc["branch"] if doc else None
            }
        }
        await broadcast_message(json.dumps(payload_remove))
        payload_toast = {
            "type": "new_notification",
            "data": {
                "id": str(doc_id),
                "message": f"Documento eliminato: {title}",
                "tipo": "documento"
            }
        }
        await broadcast_message(json.dumps(payload_toast))
    except Exception as e:
        print("[WebSocket] Errore broadcast su eliminazione documento:", e)
    return Response(status_code=200, media_type="text/plain")

@documents_router.get("/documents/list/partial", response_class=HTMLResponse)
async def list_documents_partial(
    request: Request,
    current_user = Depends(get_current_user),
    docs_coll: AsyncIOMotorCollection = Depends(get_docs_coll)
):
    try:
        employment_type = current_user.get("employment_type")
        branch = current_user.get("branch")
        role = current_user.get("role")
        if role == "admin" or not employment_type:
            filter_query = {}
        else:
            filter_query = {
                "$and": [
                    {"$or": [
                        {"branch": "*"},
                        {"branch": branch}
                    ]},
                    {"$or": [
                        {"employment_type": {"$in": [employment_type, "*"]}},
                        {"employment_type": employment_type},
                        {"employment_type": "*"}
                    ]}
                ]
            }
        documents = await docs_coll.find(filter_query).sort("uploaded_at", -1).to_list(None)
        documents = [to_str_id(doc) for doc in documents]
    except Exception as e:
        print(f"[ERROR] Errore in list_documents_partial: {e}", file=sys.stderr)
        documents = []
    return request.app.state.templates.TemplateResponse(
        "documents/list_partial.html",
        {"request": request, "documents": documents, "current_user": current_user}
    )
