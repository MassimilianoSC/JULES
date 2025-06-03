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

# Costante per il percorso base dei documenti
BASE_DOCS_DIR = Path("media/docs")   # cartella radice documenti

def to_str_id(doc: dict) -> dict:
    """Converte l'_id Mongo in stringa per i template Jinja."""
    doc["_id"] = str(doc["_id"])
    if "uploaded_at" in doc and isinstance(doc["uploaded_at"], datetime):
        doc["uploaded_at"] = doc["uploaded_at"].date().isoformat()
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
    # Salva il file fisicamente
    docs_dir = BASE_DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / file.filename
    async with aiofiles.open(dest, "wb") as out:
        await out.write(await file.read())

    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    result = await save_and_notify(
        request=request,
        collection="documents",
        payload={
            "title": title.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "tags": [tag.strip() for tag in tags.split(",")] if tags else [],
            "filename": file.filename,
            "content_type": file.content_type,
            "uploaded_at": datetime.utcnow()
        },
        tipo="documento",
        titolo=title.strip(),
        branch=branch.strip()
    )
    # Recupera l'id del documento appena creato
    db = request.app.state.db
    doc = await db.documents.find_one({"title": title.strip(), "filename": file.filename})
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "document", "object_id": doc["_id"]},
            {"$set": {
                "type": "document",
                "object_id": doc["_id"],
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "document", "object_id": doc["_id"]})
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
    show_on_home: str = Form(None)
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

    updated = await db.documents.find_one({"_id": ObjectId(doc_id)})
    resp = request.app.state.templates.TemplateResponse(
        "documents/row_partial.html",
        {"request": request, "d": updated, "user": request.state.user}
    )
    resp.headers["HX-Trigger"] = "closeModal"

    # Elimino tutte le vecchie notifiche relative a questo documento
    await db.notifiche.delete_many({"id_risorsa": str(doc_id), "tipo": "documento"})
    # Dopo l'update, crea una nuova notifica per i nuovi destinatari
    await crea_notifica(
        request=request,
        tipo="documento",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=str(doc_id),
        employment_type=employment_type_list
    )

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
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    if current_user["role"] == "admin" or not employment_type:
        mongo_filter = {}
    else:
        mongo_filter = {
            "$and": [
                {
                    "$or": [
                        {"branch": "*"},
                        {"branch": current_user["branch"]}
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
    documents = await db.documents.find(mongo_filter).sort("uploaded_at", -1).to_list(None)
    return request.app.state.templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "documents": documents,
            "current_user": current_user
        }
    )

@documents_router.delete("/documents/{doc_id}")
async def delete_document(request: Request, doc_id: str):
    db = request.app.state.db
    await db.documents.delete_one({"_id": ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id})
    # rimuovi eventuale highlight
    await db.home_highlights.delete_one({"type": "document", "object_id": ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id})
    # HTMX: una 200 basta per far sparire la <li> grazie a hx-swap="delete"
    return Response(status_code=200, media_type="text/plain")
