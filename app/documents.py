from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, Response, PlainTextResponse
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
from app.ws_broadcast import broadcast_message, broadcast_resource_event
from app.utils.notification_helpers import create_action_notification_payload, create_admin_confirmation_trigger
import os
import shutil
import json

# Costante per il percorso base dei documenti
BASE_DOCS_DIR = Path("media/docs")   # cartella radice documenti
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPES = [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document', # .docx
    'application/msword', # .doc
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', # .xlsx
    'application/vnd.ms-excel', # .xls
    'application/vnd.openxmlformats-officedocument.presentationml.presentation', # .pptx
    'application/vnd.ms-powerpoint', # .ppt
    'image/jpeg',
    'image/png'
]

def to_str_id(doc: dict) -> dict:
    """Converte l'_id Mongo in stringa per i template Jinja."""
    doc["_id"] = str(doc["_id"])
    return doc

documents_router = APIRouter(tags=["documents"])

@documents_router.post(
    "/documents/upload",
    response_class=PlainTextResponse,
    dependencies=[Depends(require_admin)]
)
async def upload_document(
    request: Request,
    title: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    tags: str = Form(None),
    file: UploadFile = File(...),
    show_on_home: str = Form(None),
    current_user: dict = Depends(get_current_user)
):
    print(f"[DEBUG] Upload documento '{title}' da utente {current_user['_id']}")
    
    show_on_home = show_on_home is not None
    
    # 1. Valida il file
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        error_trigger = {
            "showAdminConfirmation": {
                "title": "File Troppo Grande",
                "message": f"La dimensione del file supera il limite massimo di {MAX_FILE_SIZE / 1024 / 1024:.0f} MB.",
                "level": "error", "duration": 5000
            }
        }
        return Response(status_code=400, headers={"HX-Trigger": json.dumps(error_trigger)})

    if file.content_type not in ALLOWED_MIME_TYPES:
        error_trigger = {
            "showAdminConfirmation": {
                "title": "Formato File Non Valido",
                "message": "Il tipo di file non è consentito. Si prega di caricare documenti o immagini.",
                "level": "error", "duration": 5000
            }
        }
        return Response(status_code=400, headers={"HX-Trigger": json.dumps(error_trigger)})

    # 2. Salva il file fisicamente
    print(f"[DEBUG] Salvataggio file fisico")
    docs_dir = BASE_DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / file.filename
    async with aiofiles.open(dest, "wb") as out:
        await out.write(contents)

    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    
    # 3. Salva il documento in Mongo
    print(f"[DEBUG] Salvataggio documento in MongoDB")
    db = request.app.state.db
    doc = {
        "title": title.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list,
        "tags": [tag.strip() for tag in tags.split(",")] if tags else [],
        "filename": file.filename,
        "content_type": file.content_type,
        "uploaded_at": datetime.utcnow(),
        "show_on_home": show_on_home
    }
    result = await db.documents.insert_one(doc)
    doc_id = result.inserted_id

    # 4. Aggiorna home_highlights
    print(f"[DEBUG] Aggiornamento highlights")
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "document", "object_id": str(doc_id)},
            {"$set": {
                "type": "document",
                "object_id": str(doc_id),
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "document", "object_id": str(doc_id)})

    # 5. Crea la notifica
    print(f"[DEBUG] Creazione notifica")
    await crea_notifica(
        request=request,
        tipo="documento",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=str(doc_id),
        employment_type=employment_type_list
    )

    # 6. Notifica WebSocket per lo staff
    try:
        print(f"[DEBUG] Creazione notifica per nuovo documento")
        payload = create_action_notification_payload('create', 'documento', title.strip(), str(current_user["_id"]))
        print(f"[DEBUG] Payload notifica: {payload}")
        await broadcast_message(payload, branch=branch.strip(), employment_type=employment_type_list, exclude_user_id=str(current_user["_id"]))
        print(f"[DEBUG] Broadcast completato")
        
        # 7. Aggiorna highlights home
        print(f"[DEBUG] Aggiornamento highlights per creazione documento")
        if show_on_home: # Invia il broadcast solo se il documento è effettivamente in home
            payload_highlight = {
                "type": "refresh_home_highlights",
                "data": {
                    "branch": branch.strip(),
                    "employment_type": employment_type_list
                }
            }
            await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type_list)
            print(f"[DEBUG] Broadcast refresh_home_highlights inviato per i destinatari corretti.")
        else:
            print(f"[DEBUG] Il documento non è show_on_home, nessun broadcast per refresh_home_highlights.")

    except Exception as e:
        print("[WebSocket] Errore broadcast su creazione documento:", e)

    # 8. Broadcast evento risorsa
    await broadcast_resource_event(
        event="add",
        item_type="document",
        item_id=str(doc_id),
        user_id=str(current_user["_id"]),
    )

    # 9. Prepara risposta con conferma admin
    print(f"[DEBUG] Preparazione risposta")
    resp = PlainTextResponse(status_code=200)
    # Prima mostra la conferma
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', title.strip())
    # Poi chiudi la modale e fai il redirect
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirect-to-documents": "/documents"
    })
    print(f"[DEBUG] Headers risposta: {dict(resp.headers)}")
    return resp

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
    highlight = await db.home_highlights.find_one({"type": "document", "object_id": str(doc_id)})
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
    print(f"[DEBUG] Modifica documento '{title}' da utente {current_user['_id']}")
    
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    
    # 1. Aggiorna il documento
    await db.documents.update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": {
            "title": title.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "tags": [tag.strip() for tag in tags.split(",")] if tags else [],
            "show_on_home": show_on_home is not None
        }}
    )
    
    # 2. Gestione home_highlights
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "document", "object_id": str(doc_id)},
            {"$set": {
                "type": "document",
                "object_id": str(doc_id),
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "document", "object_id": str(doc_id)})

    # 3. Recupera il documento aggiornato
    updated = await db.documents.find_one({"_id": ObjectId(doc_id)})
    updated = to_str_id(updated)

    # 4. Notifica WebSocket per lo staff
    try:
        print(f"[DEBUG] Creazione notifica per modifica documento")
        payload = create_action_notification_payload('update', 'documento', title.strip(), str(current_user["_id"]))
        print(f"[DEBUG] Payload notifica: {payload}")
        await broadcast_message(payload, branch=branch.strip(), employment_type=employment_type_list, exclude_user_id=str(current_user["_id"]))
        print(f"[DEBUG] Broadcast completato")
        
        # 5. Aggiorna highlights home
        print(f"[DEBUG] Aggiornamento highlights per modifica documento")
        if show_on_home is not None: # Invia il broadcast solo se il documento è effettivamente in home
            payload_highlight = {
                "type": "refresh_home_highlights",
                "data": {
                    "branch": branch.strip(),
                    "employment_type": employment_type_list
                }
            }
            await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type_list)
            print(f"[DEBUG] Broadcast refresh_home_highlights inviato per i destinatari corretti.")
        else:
            # Se show_on_home è False (o None qui, che significa che il checkbox non era spuntato),
            # e il documento POTREBBE essere stato precedentemente in home,
            # inviamo comunque un refresh generico ai destinatari che POTEVANO vederlo,
            # così la loro home si aggiorna rimuovendolo.
            # La logica di `home_highlights_partial` poi non lo includerà.
            payload_highlight = {
                "type": "refresh_home_highlights",
                 "data": { # Usiamo i valori del documento per raggiungere chi lo vedeva prima
                    "branch": updated.get("branch", "*"), # branch precedente o attuale
                    "employment_type": updated.get("employment_type", ["*"])
                }
            }
            await broadcast_message(payload_highlight, branch=updated.get("branch", "*"), employment_type=updated.get("employment_type", ["*"]))
            print(f"[DEBUG] Documento non più show_on_home, inviato refresh_home_highlights per la rimozione.")

    except Exception as e:
        print("[WebSocket] Errore broadcast su modifica documento:", e)

    # 6. Broadcast evento risorsa
    await broadcast_resource_event(
        event="update",
        item_type="document",
        item_id=str(doc_id),
        user_id=str(current_user["_id"]),
    )

    # 7. Prepara la risposta con conferma admin
    print(f"[DEBUG] Preparazione risposta")
    resp = request.app.state.templates.TemplateResponse(
        "documents/row_partial.html",
        {"request": request, "d": updated, "user": current_user}
    )

    admin_confirmation_payload = json.loads(create_admin_confirmation_trigger('update', title.strip()))
    admin_confirmation_payload["closeModal"] = True # Aggiungiamo closeModal per il gestore globale in ui.js
    resp.headers["HX-Trigger"] = json.dumps(admin_confirmation_payload)

    print(f"[DEBUG] Headers risposta: {dict(resp.headers)}")
    
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
async def delete_document(request: Request, doc_id: str, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    
    # Recupera info documento prima di cancellarlo
    doc = await db.documents.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Documento non trovato")
    
    title = doc.get("title", "")
    branch = doc.get("branch", "*")
    employment_type = doc.get("employment_type", ["*"])
    
    # Rimuovi il file fisico
    filename = doc.get("filename")
    if filename:
        file_path = BASE_DOCS_DIR / filename
        try:
            file_path.unlink()
        except Exception as e:
            print(f"Errore rimozione file {filename}:", e)

    # Rimuovi da MongoDB
    await db.documents.delete_one({"_id": ObjectId(doc_id)})
    await db.home_highlights.delete_one({"type": "document", "object_id": str(doc_id)})

    # 1. Notifica WebSocket per lo staff
    print(f"[DEBUG] Creazione notifica per eliminazione documento '{title}' da utente {current_user['_id']}")
    payload = create_action_notification_payload('delete', 'documento', title, str(current_user["_id"]))
    print(f"[DEBUG] Payload notifica: {payload}")
    await broadcast_message(payload, branch=branch, employment_type=employment_type, exclude_user_id=str(current_user["_id"]))
    print(f"[DEBUG] Broadcast completato")

    # 2. Broadcast evento risorsa
    await broadcast_resource_event(
        event="delete",
        item_type="document",
        item_id=str(doc_id),
        user_id=str(current_user["_id"]),
    )

    # 3. Aggiorna highlights home
    try:
        # Se il documento era show_on_home, invia un broadcast mirato per refresh.
        # Gli utenti che non avevano accesso a questo branch/emp_type non riceveranno il segnale.
        # Gli utenti che avevano accesso lo riceveranno e la loro home si aggiornerà (rimuovendo il doc).
        if doc.get("show_on_home"):
            payload_highlight = {
                "type": "refresh_home_highlights",
                "data": {
                    "branch": branch, # branch del documento eliminato
                    "employment_type": employment_type # employment_type del documento eliminato
                }
            }
            await broadcast_message(payload_highlight, branch=branch, employment_type=employment_type)
            print(f"[DEBUG] Broadcast refresh_home_highlights per eliminazione inviato a branch '{branch}', emp_type '{employment_type}'.")
    except Exception as e:
        print("[WebSocket] Errore broadcast su refresh highlights dopo eliminazione documento:", e)

    # 4. Conferma per l'admin
    print(f"[DEBUG] Creazione conferma admin")
    resp = Response(status_code=200)
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('delete', title)
    print(f"[DEBUG] Headers risposta: {dict(resp.headers)}")
    
    return resp

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
