import json
from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File, Body
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, Response, PlainTextResponse, JSONResponse
from app.deps import require_admin, get_current_user, get_docs_coll, get_db
from app.utils.save_with_notifica import save_and_notify
from bson import ObjectId
from datetime import datetime, timedelta
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorCollection
import aiofiles
from mimetypes import guess_type
from app.notifiche import crea_notifica, crea_notifica_commento
from fastapi.templating import Jinja2Templates
from app.models.ai_news_model import AINewsBase, AINewsDB, CommentBase, CommentDB, ViewIn, ViewActionType
from fastapi import Query
from app.ws_broadcast import broadcast_message, broadcast_resource_event
from typing import Optional
from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import core_schema
import bleach
import re
import os
import shutil
from app.utils.notification_helpers import create_action_notification_payload, create_admin_confirmation_trigger
try:
    from markdown_it import MarkdownIt
except ImportError:
    MarkdownIt = None
from pymongo import ReturnDocument

# Costante per il percorso base dei documenti AI
BASE_AI_NEWS_DIR = Path("media/docs/ai_news")   # cartella radice documenti AI

# Costanti di configurazione
DEBOUNCE_HOURS = 24  # tempo minimo fra due view validanti

def to_str_id(doc: dict) -> dict:
    """Converte ObjectId fields in stringa per i template Jinja o JSON risposte."""
    if not doc: return doc # Handle None case

    # Convert _id first as it's common
    if "_id" in doc and isinstance(doc.get("_id"), ObjectId):
        doc["_id"] = str(doc["_id"])

    # List of fields that might contain an ObjectId and should be converted to string
    fields_to_convert = [
        "author_id", "user_id", "news_id", "parent_id",
        "comment_id", "reply_id" # Add any other relevant ObjectId fields used in your app
    ]
    for field in fields_to_convert:
        if field in doc and isinstance(doc.get(field), ObjectId):
            doc[field] = str(doc[field])

    # Format specific datetime fields if they exist
    datetime_fields_to_format = {
        "uploaded_at": lambda dt: dt.date().isoformat(), # Date only
        "created_at": lambda dt: dt.isoformat(),         # Full ISO string
        "updated_at": lambda dt: dt.isoformat(),         # Full ISO string
        "last_view": lambda dt: dt.isoformat()           # Full ISO string
    }
    for field, formatter in datetime_fields_to_format.items():
        if field in doc and isinstance(doc.get(field), datetime):
            doc[field] = formatter(doc[field])

    # Recursively process lists of dictionaries (e.g., embedded comments/replies if any)
    for key, value in doc.items():
        if isinstance(value, list):
            new_list = []
            for item in value:
                if isinstance(item, dict):
                    new_list.append(to_str_id(item.copy())) # Process a copy
                else:
                    new_list.append(item)
            doc[key] = new_list
        elif isinstance(value, dict): # Recursively process nested dictionaries
            doc[key] = to_str_id(value.copy()) # Process a copy

    return doc

ai_news_router = APIRouter(tags=["ai_news"])

# Corrected type hint for employment_type and other optional fields.
# Added current_user dependency.
# Changed response_class to Response for header manipulation.
@ai_news_router.post(
    "/ai-news/upload", # This is the "create" endpoint
    response_class=Response,
    dependencies=[Depends(require_admin)]
)
async def upload_ai_news(
    request: Request,
    title: str = Form(...),
    branch: str = Form(...),
    employment_type: List[str] = Form(...), # Expect List[str]
    tags: Optional[str] = Form(None), # Optional
    file: Optional[UploadFile] = File(None), # Optional
    external_url: Optional[str] = Form(None), # Optional
    show_on_home: bool = Form(False), # Expect bool
    category: str = Form(...),
    current_user: dict = Depends(get_current_user) # Added current_user
):
    # Ensure employment_type is a list, even if only one item is submitted via form
    # This might not be strictly necessary if using List[str] = Form(...) correctly handles single values.
    if isinstance(employment_type, str):
        employment_type_list = [emp.strip() for emp in employment_type.split(',') if emp.strip()]
    elif isinstance(employment_type, list):
        employment_type_list = [emp.strip() for emp in employment_type if emp.strip()]
    else: # Fallback, should not happen with List[str]
        employment_type_list = ['*']


    # 1. Salva il file fisicamente (se presente)
    docs_dir = BASE_AI_NEWS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    filename_on_disk = None
    file_content_type = None

    if file and file.filename:
        # Basic sanitization, consider more robust methods
        safe_filename = re.sub(r"[^\w\.-]", "_", file.filename)
        dest = docs_dir / safe_filename
        async with aiofiles.open(dest, "wb") as out:
            content = await file.read() # Read file content
            await out.write(content)   # Write to disk
        filename_on_disk = safe_filename
        file_content_type = file.content_type

    # Se non c'è né file né link, errore
    if not filename_on_disk and not (external_url and external_url.strip()):
        # This should ideally be handled by client-side validation or a Pydantic model for the form.
        # Returning an HTML error response that HTMX can display in a target.
        # Or raise HTTPException if a JSON error response is preferred for API-like behavior.
        raise HTTPException(status_code=400, detail="Devi caricare un file o inserire un link esterno.")

    db = request.app.state.db
    doc_data = {
        "title": title.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list, # Use the processed list
        "tags": [tag.strip() for tag in tags.split(",")] if tags and tags.strip() else [],
        "filename": filename_on_disk,
        "content_type": file_content_type,
        "external_url": external_url.strip() if external_url else None,
        "uploaded_at": datetime.utcnow(),
        "category": category.strip(),
        "show_on_home": show_on_home, # Store the boolean value
        "stats": {"likes": 0, "comments": 0, "replies": 0, "total_interactions": 0, "views": 0}, # Ensure views is initialized
        "author_id": current_user["_id"] # Store author ObjectId
    }
    result = await db.ai_news.insert_one(doc_data)
    new_id = str(result.inserted_id)

    # 4. Crea la notifica standard per i destinatari (non-admin)
    await crea_notifica(
        request=request,
        tipo="ai_news", # Specific type for AI News creation
        titolo=f"Nuova AI News: {title.strip()}",
        branch=branch.strip(),
        id_risorsa=new_id,
        employment_type=employment_type_list,
        source_user_id=str(current_user["_id"]) # User who performed the action
    )

    # 5. Invia WebSocket toast per non-admin
    payload_toast = create_action_notification_payload(
        'create', # Action: 'create', 'update', 'delete'
        'ai_news',   # Resource type for client-side handling
        title.strip(), # Title of the resource
        str(current_user["_id"]) # ID of the user who performed the action
    )
    await broadcast_message(
        payload_toast,
        branch=branch.strip(),
        employment_type=employment_type_list,
        exclude_user_id=str(current_user["_id"]) # Exclude the admin who created it
    )

    # 6. Broadcast dell'evento generico per aggiornare UI (es. liste)
    await broadcast_resource_event(
        event="add", # "add", "update", "delete"
        item_type="ai_news",
        item_id=new_id,
        user_id=str(current_user["_id"]),
        data_filter_criteria={"branch": branch.strip(), "employment_type": employment_type_list} # For client-side filtering
    )

    # 7. Aggiorna home_highlights se show_on_home è True
    if show_on_home:
        await db.home_highlights.insert_one({
            "type": "ai_news",
            "object_id": new_id, # Store as string ID
            "title": title.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "created_at": doc_data["uploaded_at"] # Use the same creation timestamp
        })
        # Broadcast refresh for home highlights
        payload_highlight = {
            "type": "refresh_home_highlights",
            "data": {"branch": branch.strip(), "employment_type": employment_type_list}
        }
        await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type_list)

    # 8. Risposta di conferma per l'admin con chiusura modale e redirect/refresh
    resp = Response(status_code=200) # Empty 200 OK, triggers in headers
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', title.strip())

    # HX-Trigger-After-Settle for actions after SweetAlert
    # Since this is a full page form submission, we don't need to close a modal.
    # We just redirect. The admin confirmation (SweetAlert) will show before the redirect.
    trigger_after_settle = {"redirect-to-ai-news": "/ai-news"}

    resp.headers["HX-Trigger-After-Settle"] = json.dumps(trigger_after_settle)
    return resp

@ai_news_router.get("/ai-news/new", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def new_ai_news_form(request: Request):
    branches = ["*", "HQE", "HQ ITALIA", "HQIA"]
    employment_types = ["*", "TD", "TI", "AP", "CO"]
    # Always serve the full page template for creation
    return request.app.state.templates.TemplateResponse(
        "ai_news/upload.html",
        {
            "request": request,
            "branches": branches,
            "employment_types": employment_types
        }
    )

@ai_news_router.get(
    "/ai-news/{doc_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_ai_news_form(
    request: Request,
    doc_id: str,
    user = Depends(get_current_user) # Renamed from current_user for consistency with template
):
    db = request.app.state.db
    doc = await db.ai_news.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Documento AI non trovato")

    # Convert ObjectIds to strings for template, including author_id if present
    doc = to_str_id(doc) # Handles _id and uploaded_at

    # Ensure employment_type is a list for the template's select multiple or logic
    if isinstance(doc.get("employment_type"), str):
        doc["employment_type"] = [doc["employment_type"]]
    elif not doc.get("employment_type"): # If None or empty list from DB
        doc["employment_type"] = ["*"] # Default to prevent errors in template if it expects a list

    # show_on_home is already a boolean in the DB doc due to create/update logic
    # No need to check highlights collection separately if it's stored on the doc.
    # If it's NOT stored on the doc, then this is needed:
    # highlight = await db.home_highlights.find_one({"type": "ai_news", "object_id": doc_id})
    # doc["show_on_home"] = bool(highlight)

    branches = ["*", "HQE", "HQ ITALIA", "HQIA"]
    employment_types_options = ["*", "TD", "TI", "AP", "CO"] # Options for the select

    return request.app.state.templates.TemplateResponse(
        "ai_news/edit_partial.html", # This should be the modal partial
        {
            "request": request,
            "d": doc, # Document data, 'd' as expected by current edit_partial
            "user": user, # current_user passed as 'user'
            "current_user": user, # Also pass as current_user for max compatibility
            "branches": branches,
            "employment_types": employment_types_options # Options for the dropdown
        }
    )

@ai_news_router.post(
    "/ai-news/{doc_id}/edit",
    response_class=HTMLResponse, # Will return the updated row partial
    dependencies=[Depends(require_admin)]
)
async def edit_ai_news_submit(
    request: Request,
    doc_id: str,
    title: str = Form(...),
    branch: str = Form(...),
    employment_type: List[str] = Form(...), # Expecting a list
    tags: Optional[str] = Form(None), # Optional
    category: str = Form(...),
    show_on_home: bool = Form(False), # Expecting boolean
    current_user: dict = Depends(get_current_user) # Added current_user
):
    db = request.app.state.db
    object_id_doc = ObjectId(doc_id)

    # Ensure employment_type is a list from form data
    if isinstance(employment_type, str):
        employment_type_list = [emp.strip() for emp in employment_type.split(',') if emp.strip()]
    elif isinstance(employment_type, list):
        employment_type_list = [emp.strip() for emp in employment_type if emp.strip()]
    else: # Fallback
        employment_type_list = ['*']

    # Fetch the document *before* update to compare old/new recipient criteria if needed for notifications.
    # For simplicity now, we'll notify based on new criteria.
    # original_doc = await db.ai_news.find_one({"_id": object_id_doc})

    update_data = {
        "title": title.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list,
        "tags": [tag.strip() for tag in tags.split(",")] if tags and tags.strip() else [],
        "category": category.strip(),
        "show_on_home": show_on_home # Storing the boolean directly
        # Not updating filename or external_url in edit form, these are fixed at creation.
    }
    await db.ai_news.update_one(
        {"_id": object_id_doc},
        {"$set": update_data}
    )

    # Create notification for non-admins (consider if recipients changed significantly)
    # Using a generic "update" type notification for now.
    await crea_notifica(
        request=request,
        tipo="ai_news_update", # Potentially a different type for updates
        titolo=f"AI News aggiornata: {title.strip()}",
        branch=branch.strip(),
        id_risorsa=doc_id, # doc_id is already string
        employment_type=employment_type_list,
        source_user_id=str(current_user["_id"])
    )

    # WebSocket toast for non-admin users
    payload_toast = create_action_notification_payload(
        'update', # Action
        'ai_news',   # Resource type
        title.strip(), # Title
        str(current_user["_id"]) # User ID
    )
    await broadcast_message(
        payload_toast,
        branch=branch.strip(),
        employment_type=employment_type_list,
        exclude_user_id=str(current_user["_id"])
    )

    # Home Highlights Management
    # Fetch the *updated* document to get its creation date for highlights consistency
    # (or pass original_doc.get("uploaded_at") if fetched before update)
    updated_doc_for_highlight = await db.ai_news.find_one({"_id": object_id_doc})
    created_at_for_highlight = updated_doc_for_highlight.get("uploaded_at", datetime.utcnow())

    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "ai_news", "object_id": doc_id}, # Use string doc_id for consistency if object_id is string
            {"$set": {
                "type": "ai_news", "object_id": doc_id, "title": title.strip(),
                "branch": branch.strip(), "employment_type": employment_type_list,
                "created_at": created_at_for_highlight
            }},
            upsert=True
        )
    else: # If not show_on_home, ensure it's removed from highlights
        await db.home_highlights.delete_one({"type": "ai_news", "object_id": doc_id})

    # Always broadcast highlight refresh to relevant users as criteria might have changed
    # or item added/removed from home.
    payload_highlight_refresh = {
        "type": "refresh_home_highlights",
        # Send new criteria. If item removed, users matching old criteria also need refresh.
        # This might require fetching original_doc for old criteria if they could change.
        # For now, simplifying to new criteria.
        "data": {"branch": branch.strip(), "employment_type": employment_type_list}
    }
    await broadcast_message(payload_highlight_refresh, branch=branch.strip(), employment_type=employment_type_list)


    # WebSocket event for UI update (e.g., refreshing the specific row in a list)
    await broadcast_resource_event(
        event="update",
        item_type="ai_news",
        item_id=doc_id, # doc_id is already string
        user_id=str(current_user["_id"]),
        # Pass data that might be needed by client to update the row, or client refetches
        data_filter_criteria={"branch": branch.strip(), "employment_type": employment_type_list}
    )

    # Return the updated row partial
    updated_doc_for_template = await db.ai_news.find_one({"_id": object_id_doc})
    updated_doc_for_template = to_str_id(updated_doc_for_template.copy()) # Ensure all IDs are strings for template

    # Ensure employment_type is a list for the template, even if single from DB after update
    if isinstance(updated_doc_for_template.get("employment_type"), str):
         updated_doc_for_template["employment_type"] = [updated_doc_for_template["employment_type"]]
    elif not updated_doc_for_template.get("employment_type"): # Handle None or empty list
         updated_doc_for_template["employment_type"] = ["*"]


    resp = request.app.state.templates.TemplateResponse(
        "ai_news/row_partial.html",
        {"request": request, "d": updated_doc_for_template, "current_user": current_user, "user": current_user}
    )

    # Admin confirmation + close modal trigger
    admin_confirm_trigger = create_admin_confirmation_trigger('update', title.strip())
    # Combine with closeModal: parse the JSON, add key, then stringify
    trigger_data = json.loads(admin_confirm_trigger) # Assuming it's a JSON string like {"showAdminConfirmation": {...}}
    trigger_data["closeModal"] = "true" # Add closeModal to the same trigger object
    resp.headers["HX-Trigger"] = json.dumps(trigger_data)

    return resp

@ai_news_router.get("/ai-news/{doc_id}/download")  # Modificato da /ai-news/{doc_id}
async def download_ai_news(doc_id: str, request: Request):
    db = request.app.state.db
    doc = await db.ai_news.find_one({"_id": doc_id})
    if not doc and ObjectId.is_valid(doc_id):
        doc = await db.ai_news.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento AI non trovato")
    file_path = BASE_AI_NEWS_DIR / doc["filename"]
    if not file_path.exists():
        raise HTTPException(404, "File non trovato")
    return FileResponse(path=file_path, filename=doc["filename"], media_type=doc.get("content_type", "application/octet-stream"))

@ai_news_router.get("/api/ai-news/{doc_id}/preview")
async def preview_ai_news(doc_id: str, request: Request):
    db = request.app.state.db
    doc = await db.ai_news.find_one({"_id": doc_id})
    if not doc and ObjectId.is_valid(doc_id):
        doc = await db.ai_news.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento AI non trovato")
    # Primo caso: struttura nuova (content.type == file)
    if doc.get("content", {}).get("type") == "file" and doc.get("content", {}).get("filename"):
        filename = doc["content"]["filename"]
    # Secondo caso: struttura vecchia (filename a livello root)
    elif doc.get("filename"):
        filename = doc["filename"]
    else:
        raise HTTPException(status_code=400, detail="Tipo di contenuto non supportato per l'anteprima")
    file_path = BASE_AI_NEWS_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "File non trovato")
    mime, _ = guess_type(str(file_path))
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=mime or "application/octet-stream",
        headers=headers
    )

@ai_news_router.get("/ai-news", response_class=HTMLResponse)
async def list_ai_news(
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
    ai_news = await db.ai_news.find(mongo_filter).sort("uploaded_at", -1).to_list(None)
    # Aggiungi lo stato dei like per ogni notizia
    for news in ai_news:
        user_like = await db.ai_news_likes.find_one({
            "news_id": ObjectId(news["_id"]),
            "user_id": ObjectId(current_user["_id"])
        })
        news["user_liked"] = bool(user_like)
    return request.app.state.templates.TemplateResponse(
        "ai_news.html",
        {
            "request": request,
            "ai_news": ai_news,
            "user": current_user
        }
    )

@ai_news_router.delete("/ai-news/{doc_id}", response_class=Response) # Ensure response_class=Response for header manipulation
async def delete_ai_news(
    request: Request, 
    doc_id: str, # doc_id is a string from path
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    
    try:
        object_id_to_delete = ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID documento non valido.")

    doc_to_delete = await db.ai_news.find_one({"_id": object_id_to_delete})
    if not doc_to_delete:
        raise HTTPException(status_code=404, detail="Documento AI non trovato.")

    title = doc_to_delete.get('title', 'Documento AI sconosciuto')
    branch = doc_to_delete.get('branch', '*')
    # Ensure employment_type is a list for broadcast
    employment_type_from_doc = doc_to_delete.get('employment_type', ['*'])
    if isinstance(employment_type_from_doc, str): # Defensive check
        employment_type_from_doc = [employment_type_from_doc]


    # Delete physical file if it exists and filename is present
    if doc_to_delete.get("filename"):
        file_path = BASE_AI_NEWS_DIR / doc_to_delete["filename"]
        if file_path.exists():
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}") # Log error but continue deletion

    # Delete the document from DB
    await db.ai_news.delete_one({"_id": object_id_to_delete})

    # Remove from home_highlights (use string doc_id as object_id is stored as string there)
    await db.home_highlights.delete_one({"type": "ai_news", "object_id": doc_id})

    # 1. WebSocket for non-admin toast notification
    payload_toast = create_action_notification_payload(
        'delete', # action
        'ai_news',   # resource_type
        title,    # resource_title
        str(current_user["_id"]) # user_id
    )
    await broadcast_message(
        payload_toast,
        branch=branch, # Use branch from the deleted doc
        employment_type=employment_type_from_doc, # Use employment_type from the deleted doc
        exclude_user_id=str(current_user["_id"])
    )

    # 2. WebSocket for UI update (list refresh / row removal)
    await broadcast_resource_event(
        event="delete",
        item_type="ai_news",
        item_id=doc_id, # doc_id is already a string here
        user_id=str(current_user["_id"]),
        # Pass criteria of the deleted item so clients can filter if necessary
        data_filter_criteria={"branch": branch, "employment_type": employment_type_from_doc}
    )

    # 3. Refresh highlights if it was on home (or just always refresh for relevant users)
    # No need to check was_on_home, just send refresh to those who might have seen it based on its criteria
    payload_highlight_refresh = {
        "type": "refresh_home_highlights",
        "data": {"branch": branch, "employment_type": employment_type_from_doc}
    }
    await broadcast_message(payload_highlight_refresh, branch=branch, employment_type=employment_type_from_doc)

    # 4. Admin confirmation via HX-Trigger
    resp = Response(status_code=200) # HTMX expects 200 for swap, even on delete if hx-target is used for row removal
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('delete', title)
    # The row will be removed by `hx-swap="delete"` on the client side (if form has hx-target)
    # or by JS handling the broadcast_resource_event.
    return resp

@ai_news_router.get("/api/ai-news")
async def list_ai_news_api(
    request: Request,
    current_user = Depends(get_current_user),
    skip: int = 0,
    limit: int = 20,
    section: Optional[str] = None,
    branch: Optional[str] = None,
    search: Optional[str] = None
):
    db = request.app.state.db
    mongo_filter = {}
    employment_type = current_user.get("employment_type")
    if current_user["role"] != "admin" and employment_type:
        mongo_filter["employment_type"] = {"$in": ["*", employment_type]}
    if section:
        mongo_filter["section"] = section
    if branch:
        mongo_filter["branch"] = branch
    if search:
        mongo_filter["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}}
        ]
    cursor = db.ai_news.find(mongo_filter)
    total = await db.ai_news.count_documents(mongo_filter)
    news = await cursor.sort("uploaded_at", -1).skip(skip).limit(limit).to_list(None)
    for doc in news:
        doc["_id"] = str(doc["_id"])
        doc["author_id"] = str(doc["author_id"])
    return {
        "total": total,
        "items": news,
        "skip": skip,
        "limit": limit
    }

@ai_news_router.post("/api/ai-news", dependencies=[Depends(require_admin)])
async def create_ai_news_api(
    request: Request,
    news: AINewsBase,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    news_doc = news.model_dump()
    news_doc["author_id"] = ObjectId(current_user["_id"])
    news_doc["uploaded_at"] = datetime.utcnow()
    news_doc["stats"] = {"views": 0, "likes": 0, "comments": 0}
    result = await db.ai_news.insert_one(news_doc)
    await crea_notifica(
        request=request,
        tipo="ai_news",
        titolo=news.title,
        branch=news.branch,
        id_risorsa=str(result.inserted_id),
        employment_type=news.employment_type
    )
    await broadcast_message(f"new:ai_news:{str(result.inserted_id)}")
    return {"id": str(result.inserted_id)}

@ai_news_router.get("/api/ai-news/{news_id}")
async def get_ai_news_api(
    news_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    news = await db.ai_news.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(status_code=404, detail="News non trovata")
    employment_type = current_user.get("employment_type")
    if current_user["role"] != "admin" and employment_type:
        if news["employment_type"] not in ["*", employment_type]:
            raise HTTPException(status_code=403, detail="Accesso non consentito")
    news["_id"] = str(news["_id"])
    news["author_id"] = str(news["author_id"])
    return news

class AINewsUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    section: Optional[str] = None
    branch: Optional[str] = None
    employment_type: Optional[str] = None
    tags: Optional[list] = None
    content: Optional[dict] = None
    content_type: Optional[str] = None
    show_on_home: Optional[bool] = None
    metadata: Optional[dict] = None

@ai_news_router.patch("/api/ai-news/{news_id}", dependencies=[Depends(require_admin)])
async def update_ai_news_api(
    news_id: str,
    news_update: AINewsUpdate,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    existing = await db.ai_news.find_one({"_id": ObjectId(news_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="News non trovata")
    update_data = {k: v for k, v in news_update.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        return {"modified_count": 0}
    result = await db.ai_news.update_one(
        {"_id": ObjectId(news_id)},
        {"$set": update_data}
    )
    await broadcast_message(f"update:ai_news:{news_id}")
    return {"modified_count": result.modified_count}

@ai_news_router.post("/{news_id}/view")
async def add_view(
    news_id: str,
    payload: ViewIn,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    # ── 1. gli admin non contano ----------------------------------
    if current_user.get("role") == "admin":
        return {"success": True, "debounced": True}

    now = datetime.utcnow()
    threshold = now - timedelta(hours=DEBOUNCE_HOURS)

    db = request.app.state.db
    views_col = db.ai_news_views
    news_col = db.ai_news

    # ── 2. upsert + check last_view -------------------------------
    result = await views_col.find_one_and_update(
        {"user_id": current_user["_id"], "news_id": ObjectId(news_id)},
        {
            # se il documento NON esiste -> inserisci ora
            "$setOnInsert": {"action": payload.action_type, "last_view": now},
            # se esiste ed è vecchio -> aggiorna last_view
            "$set": {"last_view": now}
        },
        upsert=True,
        return_document=ReturnDocument.BEFORE  # ottieni doc PRIMA dell'update
    )

    # result == None  → era un inserimento; contatore da incrementare
    # result.last_view < threshold → contatore da incrementare
    # altrimenti debounce
    should_increment = (
        result is None or
        result["last_view"] < threshold
    )

    if not should_increment:
        print("[DEBUG_AI_NEWS] view debounced")
        return {"success": True, "debounced": True}

    # ── 3. incrementa il campo views sulla news -------------------
    update = {"$inc": {"stats.views": 1}}
    new_doc = await news_col.find_one_and_update(
        {"_id": ObjectId(news_id)},
        update,
        return_document=ReturnDocument.AFTER,
        projection={"stats.views": 1}
    )
    new_total = new_doc["stats"]["views"]

    # ── 4. broadcast realtime a tutti i client --------------------
    await broadcast_message({
        "type": "view/update",
        "news_id": news_id,
        "views": new_total
    })

    return {"success": True, "views": new_total}

@ai_news_router.post("/api/ai-news/{news_id}/like")
async def toggle_ai_news_like(
    news_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    existing_like = await db.ai_news_likes.find_one({
        "news_id": ObjectId(news_id),
        "user_id": ObjectId(current_user["_id"])
    })
    if existing_like:
        await db.ai_news_likes.delete_one({"_id": existing_like["_id"]})
        inc_value = -1
    else:
        like_doc = {
            "news_id": ObjectId(news_id),
            "user_id": ObjectId(current_user["_id"]),
            "timestamp": datetime.utcnow()
        }
        await db.ai_news_likes.insert_one(like_doc)
        inc_value = 1
    # Aggiorna le statistiche
    await db.ai_news.update_one(
        {"_id": ObjectId(news_id)},
        {"$inc": {"stats.likes": inc_value}}
    )
    # Recupera i dati aggiornati
    news = await db.ai_news.find_one({"_id": ObjectId(news_id)})
    # Invia messaggio WebSocket
    await broadcast_message(json.dumps({
        "type": "stats:ai_news",
        "data": {"news_id": str(news_id), "action": "like"}
    }))
    return {
        "stats": news.get("stats", {"likes": 0}),
        "user_has_liked": inc_value > 0
    }

@ai_news_router.get("/api/ai-news/{news_id}/stats")
async def get_stats(
    news_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    
    # Conta i commenti
    total_comments = await db.ai_news_comments.count_documents({"news_id": ObjectId(news_id)})
    
    return JSONResponse({
        "comments": total_comments
    })

@ai_news_router.get("/api/ai-news/{news_id}/comments")
async def get_comments(
    request: Request,
    news_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=20),
    db = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        news_oid = ObjectId(news_id)
        skip = (page - 1) * page_size
        total_count = await db.ai_news_comments.count_documents({"news_id": news_oid})
        comments = await db.ai_news_comments.find(
            {"news_id": news_oid}
        ).sort(
            [("created_at", 1)]
        ).skip(skip).limit(page_size).to_list(None)
        # Popola le informazioni degli autori
        user_ids = [ObjectId(comment["author_id"]) for comment in comments]
        users = await db.users.find({"_id": {"$in": user_ids}}).to_list(None)
        # Converti gli ObjectId in stringhe nel dizionario users
        users_map = {}
        for user in users:
            user["_id"] = str(user["_id"])
            users_map[user["_id"]] = user
        for comment in comments:
            comment["_id"] = str(comment["_id"])
            comment["news_id"] = str(comment["news_id"])
            comment["author_id"] = str(comment["author_id"])
            if "parent_id" in comment and comment["parent_id"] is not None:
                comment["parent_id"] = str(comment["parent_id"])
            if "reply_to" in comment and comment["reply_to"] is not None:
                comment["reply_to"] = str(comment["reply_to"])
            author_id = str(comment["author_id"])
            comment["author"] = users_map.get(author_id, {"name": "Utente eliminato"})
        # Se non è una richiesta HTMX, restituisci JSON
        if "HX-Request" not in request.headers:
            return {
                "items": comments,
                "total_count": total_count,
                "has_more": total_count > (skip + len(comments))
            }
        # Renderizza il template con i commenti
        return request.app.state.templates.TemplateResponse(
            "ai_news/comments_list_partial.html",
            {
                "request": request,
                "messages": comments,
                "news_id": news_id,
                "user": current_user,
                "page_size": page_size,
                "current_page": page,
                "total_comments": total_count,
                "has_more": total_count > (skip + len(comments)),
                "users": users  # Per le menzioni
            }
        )
    except Exception as e:
        print(f"[ERROR] Errore nel caricamento dei commenti: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@ai_news_router.post("/api/ai-news/{news_id}/comments", dependencies=[Depends(get_current_user)])
async def add_comment(
    news_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    data = await request.json()
    
    # Verifica che la news esista
    news = await db.ai_news.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(status_code=404, detail="News non trovata")
    
    data = await request.json() # Assicuriamoci che data sia definito qui
    parent_id_str = data.get("parentId") # Il frontend potrebbe inviare parentId per le risposte

    # Crea il commento
    ALLOWED_TAGS_COMMENT = ['a', 'b', 'strong', 'i', 'em', 'u', 'br', 'p']
    ALLOWED_ATTRIBUTES_COMMENT = {'a': ['href', 'title', 'target']}

    sanitized_content = bleach.clean(
        data["content"],
        tags=ALLOWED_TAGS_COMMENT,
        attributes=ALLOWED_ATTRIBUTES_COMMENT,
        strip=True
    )

    comment = {
        "_id": ObjectId(),
        "news_id": ObjectId(news_id),
        "user_id": current_user["_id"],
        "content": sanitized_content, # Usa il contenuto sanitizzato
        "created_at": datetime.utcnow(),
        "likes": [],
        "replies_count": 0
    }
    if parent_id_str and ObjectId.is_valid(parent_id_str):
        comment["parent_id"] = ObjectId(parent_id_str)
        comment["news_id"] = news["_id"] # Assicura che news_id sia ObjectId della news padre
    
    await db.ai_news_comments.insert_one(comment)
    
    # Aggiorna le statistiche
    await db.ai_news.update_one(
        {"_id": ObjectId(news_id)},
        {"$inc": {"stats.comments": 1}}
    )
    
    # Calcola il nuovo totale
    new_total = await db.ai_news_comments.count_documents({"news_id": ObjectId(news_id)})
    
    # Prepara il commento per il frontend
    comment_out = {
        **comment, # commento appena inserito nel DB, che include già content sanitizzato
        "_id": str(comment["_id"]),
        "news_id": str(comment["news_id"]),
        "author_id": str(comment["user_id"]), # Manteniamo author_id per coerenza
        "created_at": comment["created_at"].isoformat(),
        # "content" è già in comment ed è quello sanitizzato
        "author": { # Standardizzato a "author"
            "_id": str(current_user["_id"]),
            "name": current_user["name"],
            "avatar": current_user.get("avatar", "")
        },
        "likes": comment.get("likes", []), # Assicurati che likes sia presente
        "replies_count": comment.get("replies_count", 0) # Assicurati che replies_count sia presente
    }
    
    # Invia il nuovo payload WebSocket unificato
    parent_replies_count_updated = 0

    # --- Creazione Notifiche Specifiche per Commenti/Risposte/Menzioni ---
    await crea_notifica_commento(
        request=request,
        news_id=news_id, # String ID della news
        comment_id=str(comment["_id"]), # String ID del commento/risposta appena creato
        author_id=str(current_user["_id"]), # String ID dell'autore del commento/risposta
        parent_id=parent_id_str if parent_id_str and ObjectId.is_valid(parent_id_str) else None,
        mentioned_users=data.get("mentions", []) # Lista di string ID utenti menzionati
    )
    # --- Fine Creazione Notifiche Specifiche ---

    if parent_id_str and ObjectId.is_valid(parent_id_str):
        # Incrementa replies_count del genitore e recupera il conteggio aggiornato
        parent_comment_updated = await db.ai_news_comments.find_one_and_update(
            {"_id": ObjectId(parent_id_str)},
            {"$inc": {"replies_count": 1}},
            return_document=ReturnDocument.AFTER,
            projection={"replies_count": 1}
        )
        if parent_comment_updated:
            parent_replies_count_updated = parent_comment_updated.get("replies_count", 0)

        # Invia messaggio specifico per l'aggiunta di una risposta
        await broadcast_message({
            "type": "reply/add",
            "data": {
                "news_id": news_id,
                "parent_id": parent_id_str,
                "reply": comment_out, # comment_out ora contiene la risposta
                "parent_replies_count": parent_replies_count_updated
            }
        })
    else:
        # È un commento principale
        await broadcast_message({
            "type": "comment/add",
            "data": { # Avvolgiamo in 'data' per coerenza con 'reply/add'
                "news_id": news_id,
                "comment": comment_out,
                "author_id": str(current_user["_id"]), # Rinominato da 'author' per chiarezza
                "total_comments": new_total # Rinominato da 'total'
            }
        })
    
    return JSONResponse(comment_out)

@ai_news_router.delete("/api/ai-news/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    comment = await db.ai_news_comments.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(status_code=404, detail="Commento non trovato")
    
    # Verifica autorizzazione
    if str(comment["user_id"]) != str(current_user["_id"]) and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Non autorizzato")

    news_id_obj = comment["news_id"] # Salva l'ObjectId della news

    # --- Inizio Eliminazione a Cascata ---
    # 1. Trova e elimina tutte le risposte al commento principale
    replies_to_delete_cursor = db.ai_news_comments.find({"parent_id": ObjectId(comment_id)})
    replies_to_delete = await replies_to_delete_cursor.to_list(None)
    
    num_replies_deleted = 0
    if replies_to_delete:
        reply_ids_to_delete = [reply["_id"] for reply in replies_to_delete]
        delete_result = await db.ai_news_comments.delete_many({"_id": {"$in": reply_ids_to_delete}})
        num_replies_deleted = delete_result.deleted_count

        # Invia messaggi WebSocket per ogni risposta eliminata
        for reply in replies_to_delete:
            # Per aggiornare il conteggio sul genitore (che sta per essere eliminato),
            # non è strettamente necessario, ma per coerenza di evento.
            # Dato che il genitore viene eliminato, il suo replies_count non è più rilevante.
            # Potremmo inviare parent_replies_count = 0 o ometterlo.
            await broadcast_message({
                "type": "reply/delete",
                "data": {
                    "news_id": str(news_id_obj),
                    "parent_id": str(comment_id), # Il commento che stiamo eliminando è il genitore di queste risposte
                    "reply_id": str(reply["_id"]),
                    "parent_replies_count": 0 # Il genitore sta scomparendo
                }
            })
    # --- Fine Eliminazione a Cascata ---

    # 2. Elimina il commento genitore
    await db.ai_news_comments.delete_one({"_id": ObjectId(comment_id)})
    num_parent_deleted = 1

    # 3. Aggiorna le statistiche sulla news
    total_comments_deleted = num_parent_deleted + num_replies_deleted
    await db.ai_news.update_one(
        {"_id": news_id_obj},
        {"$inc": {"stats.comments": -total_comments_deleted}}
    )

    # 4. Invia messaggio WebSocket per l'eliminazione del commento genitore
    # Calcola il nuovo totale dei commenti per la news (dopo tutte le eliminazioni)
    new_total_comments_for_news = await db.ai_news_comments.count_documents({"news_id": news_id_obj})
    
    await broadcast_message({
        "type": "comment/delete", # Evento per il commento genitore
        "data": { # Struttura dati unificata
            "news_id": str(news_id_obj),
            "comment_id": str(comment_id),
            "author_id": str(comment["user_id"]), # Autore del commento eliminato
            "total_comments": new_total_comments_for_news, # Conteggio aggiornato per la news
            "deleted_replies_count": num_replies_deleted # Info aggiuntiva
        }
    })
    
    # Se il commento eliminato era esso stesso una risposta, aggiorna il conteggio del SUO genitore
    if comment.get("parent_id"):
        parent_of_deleted_comment_updated = await db.ai_news_comments.find_one_and_update(
            {"_id": comment["parent_id"]},
            {"$inc": {"replies_count": -1}},
            return_document=ReturnDocument.AFTER,
            projection={"replies_count": 1}
        )
        if parent_of_deleted_comment_updated:
            # Invia un evento per aggiornare il conteggio delle risposte del nonno
            await broadcast_message({
                "type": "reply/count_update", # Evento generico per aggiornare il conteggio risposte
                "data": {
                    "news_id": str(news_id_obj),
                    "parent_id": str(comment["parent_id"]), # Il genitore del commento che abbiamo appena eliminato
                    "parent_replies_count": parent_of_deleted_comment_updated.get("replies_count", 0)
                }
            })

    return Response(status_code=204)

@ai_news_router.post("/api/ai-news/comments/{comment_id}/like")
async def toggle_comment_like(
    comment_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    comment = await db.ai_news_comments.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(status_code=404, detail="Commento non trovato")
    existing_like = await db.ai_news_comment_likes.find_one({
        "comment_id": ObjectId(comment_id),
        "user_id": ObjectId(current_user["_id"])
    })
    if existing_like:
        await db.ai_news_comment_likes.delete_one({"_id": existing_like["_id"]})
        inc_value = -1
    else:
        like_doc = {
            "comment_id": ObjectId(comment_id),
            "user_id": ObjectId(current_user["_id"]),
            "news_id": comment["news_id"],
            "timestamp": datetime.utcnow()
        }
        await db.ai_news_comment_likes.insert_one(like_doc)
        inc_value = 1
    await db.ai_news_comments.update_one(
        {"_id": ObjectId(comment_id)},
        {"$inc": {"likes": inc_value}}
    )
    # Recupera il nuovo conteggio likes
    updated_comment_for_stats = await db.ai_news_comments.find_one({"_id": comment_oid}, {"likes_count": 1, "news_id": 1}) # Ensure news_id is projected
    new_likes_count = updated_comment_for_stats.get("likes_count", 0)
    # Ensure news_id for broadcast is from the authoritative source (the comment document itself)
    news_id_for_broadcast = str(updated_comment_for_stats.get("news_id", target_comment["news_id"]))


    await broadcast_message(json.dumps({
        "type": "comment/like_update",
        "data": {
            "news_id": news_id_for_broadcast,
            "comment_id": comment_id,
            "likes_count": new_likes_count,
        }
    }))
    # The HTTP response for the user who clicked the button
    return request.app.state.templates.TemplateResponse(
        "ai_news/_like_button_partial.html", # Render the button partial
        {
            "request": request,
            "news_id": news_id_for_broadcast,
            "comment_id": comment_id,
            "likes_count": new_likes_count,
            "user_has_liked": user_has_liked_now,
            "current_user_id_str": str(current_user["_id"]) # For the macro context
        }
    )

@ai_news_router.patch("/api/ai-news/comments/{comment_id}")
async def update_comment(
    comment_id: str,
    comment_update: CommentBase,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    comment = await db.ai_news_comments.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(status_code=404, detail="Commento non trovato")
    if str(comment["author_id"]) != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Non autorizzato")

    ALLOWED_TAGS_COMMENT = ['a', 'b', 'strong', 'i', 'em', 'u', 'br', 'p']
    ALLOWED_ATTRIBUTES_COMMENT = {'a': ['href', 'title', 'target']}

    sanitized_content = bleach.clean(
        comment_update.content,
        tags=ALLOWED_TAGS_COMMENT,
        attributes=ALLOWED_ATTRIBUTES_COMMENT,
        strip=True
    )

    update_data = {
        "content": sanitized_content, # Usa il contenuto sanitizzato
        "metadata": comment_update.metadata,
        "updated_at": datetime.utcnow()
    }
    result = await db.ai_news_comments.update_one(
        {"_id": ObjectId(comment_id)},
        {"$set": update_data}
    )
    await broadcast_message(json.dumps({
        "type": "comment:ai_news",
        "data": {
            "ai_news_id": str(comment["news_id"]),
            "comment_id": str(comment["_id"]),
            "action": "update"
        }
    }))
    return {"modified_count": result.modified_count}

# --- ENDPOINT LIKE RISPOSTA ---
@ai_news_router.post("/api/ai-news/replies/{reply_id}/like")
async def toggle_reply_like(
    reply_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    reply = await db.ai_news_comments.find_one({"_id": ObjectId(reply_id)})
    if not reply or not reply.get("parent_id"):
        raise HTTPException(status_code=404, detail="Risposta non trovata")
    existing_like = await db.ai_news_reply_likes.find_one({
        "reply_id": ObjectId(reply_id),
        "user_id": ObjectId(current_user["_id"])
    })
    if existing_like:
        await db.ai_news_reply_likes.delete_one({"_id": existing_like["_id"]})
        inc_value = -1
    else:
        like_doc = {
            "reply_id": ObjectId(reply_id),
            "user_id": ObjectId(current_user["_id"]),
            "news_id": reply["news_id"],
            "timestamp": datetime.utcnow()
        }
        await db.ai_news_reply_likes.insert_one(like_doc)
        inc_value = 1
    await db.ai_news_comments.update_one(
        {"_id": ObjectId(reply_id)},
        {"$inc": {"likes": inc_value}}
    )
    await broadcast_message(json.dumps({
        "type": "comment:ai_news",
        "data": {
            "ai_news_id": str(reply["news_id"]),
            "comment_id": str(reply["_id"]),
            "action": "like"
        }
    }))
    # Ritorna il nuovo conteggio likes
    updated = await db.ai_news_comments.find_one({"_id": ObjectId(reply_id)})
    return {"liked": inc_value > 0, "likes": updated.get("likes", 0)}

# --- ENDPOINT ELIMINAZIONE RISPOSTA ---
@ai_news_router.delete("/api/ai-news/replies/{reply_id}")
async def delete_reply(
    reply_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    reply = await db.ai_news_comments.find_one({"_id": ObjectId(reply_id)})
    if not reply or not reply.get("parent_id"):
        raise HTTPException(status_code=404, detail="Risposta non trovata")
    if str(reply["author_id"]) != str(current_user["_id"]) and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Non autorizzato")
    await db.ai_news_comments.delete_one({"_id": ObjectId(reply_id)})
    # Decrementa replies_count sul commento padre
    await db.ai_news_comments.update_one(
        {"_id": reply["parent_id"]},
        {"$inc": {"replies_count": -1}},
        return_document=ReturnDocument.AFTER,
        projection={"replies_count": 1}
    )
    parent_replies_count_updated = parent_comment_updated.get("replies_count", 0) if parent_comment_updated else 0

    await broadcast_message({ # Modificato per usare la struttura definita
        "type": "reply/delete",
        "data": {
            "news_id": str(reply["news_id"]),
            "parent_id": str(reply["parent_id"]),
            "reply_id": reply_id, # reply_id è già una stringa
            "parent_replies_count": parent_replies_count_updated
        }
    })
    return {"success": True}

@ai_news_router.post("/api/markdown-preview", response_class=PlainTextResponse)
async def markdown_preview(request: Request):
    data = await request.json()
    text = data.get("text", "")
    if MarkdownIt is None:
        return "<em>Markdown non disponibile</em>"
    md = MarkdownIt("commonmark", {'breaks': True, 'html': False})
    html = md.render(text)
    # Sanitize output
    safe_html = bleach.clean(html, tags=[
        'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'strong', 'ul', 'p', 'pre', 'br', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'
    ], attributes={'a': ['href', 'title', 'target'], 'span': ['class']}, strip=True)
    return safe_html

@ai_news_router.get("/api/ai-news/{news_id}/comments/count")
async def get_comments_count(
    news_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    count = await db.ai_news_comments.count_documents({"news_id": ObjectId(news_id)})
    return {"count": count}

@ai_news_router.get("/api/users/mentions")
async def get_mentionable_users(request: Request, current_user = Depends(get_current_user)):
    users = await request.app.state.db.users.find(
        {"active": True},
        {"_id": 1, "name": 1, "email": 1}
    ).to_list(length=None)
    return [{
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"]
    } for user in users]

@ai_news_router.get("/api/users/search")
async def search_users(
    request: Request,
    q: str = Query(..., min_length=1),
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    # Cerca utenti attivi che matchano la query nel nome
    users = await db.users.find({
        "active": True,
        "name": {"$regex": q, "$options": "i"}
    }).limit(5).to_list(None)
    # Formatta i risultati
    results = [{
        "_id": str(user["_id"]),
        "name": user["name"],
        "avatar": user.get("avatar")
    } for user in users]
    return results

# Aggiorna la definizione di PyObjectId per compatibilità Pydantic v2
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.str_schema(),
            ]),
            serialization=core_schema.plain_serializer_function_schema(
                lambda x: str(x)
            )
        )

@ai_news_router.get("/api/ai-news/{news_id}/comments/{comment_id}/replies")
async def get_comment_replies(
    request: Request,
    news_id: str,
    comment_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=20),
    db = Depends(get_docs_coll),
    current_user = Depends(get_current_user)
):
    try:
        # Converti gli ID in ObjectId
        news_oid = ObjectId(news_id)
        comment_oid = ObjectId(comment_id)
        
        # Verifica l'esistenza del commento padre
        parent = await db.ai_news_comments.find_one({"_id": comment_oid})
        if not parent:
            raise HTTPException(404, "Commento non trovato")
        
        # Calcola l'offset per la paginazione
        skip = (page - 1) * page_size
        
        # Recupera le risposte paginate
        replies = await db.ai_news_comments.find({
            "news_id": news_oid,
            "parent_id": comment_oid
        }).sort(
            [("created_at", 1)]  # Dal più vecchio al più nuovo
        ).skip(skip).limit(page_size).to_list(None)
        
        # Conta il totale delle risposte per questo commento
        total_replies = await db.ai_news_comments.count_documents({
            "news_id": news_oid,
            "parent_id": comment_oid
        })
        
        # Popola le informazioni degli autori
        user_ids = [ObjectId(reply["author_id"]) for reply in replies]
        users = await db.users.find({"_id": {"$in": user_ids}}).to_list(None)
        users_map = {str(user["_id"]): user for user in users}
        
        for reply in replies:
            author_id = str(reply["author_id"])
            reply["author"] = users_map.get(author_id, {"name": "Utente eliminato"})
            
            # Converti gli ObjectId in stringhe per il template
            reply["_id"] = str(reply["_id"])
            reply["author_id"] = str(reply["author_id"])
            reply["parent_id"] = str(reply["parent_id"])
        
        # Calcola se ci sono altre risposte da caricare
        has_more = total_replies > (skip + len(replies))
        
        # Renderizza il template con le risposte
        return request.app.state.templates.TemplateResponse(
            "ai_news/comments_list_partial.html",
            {
                "request": request,
                "messages": replies,
                "news_id": news_id,
                "parent_id": comment_id,
                "user": current_user,
                "page_size": page_size,
                "current_page": page,
                "total_replies": total_replies,
                "has_more": has_more,
                "users": users  # Per le menzioni
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ai_news_router.get("/ai-news/{news_id}")
async def view_ai_news(
    request: Request,
    news_id: str,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    news = await db.ai_news.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(status_code=404, detail="News non trovata")
    employment_type = current_user.get("employment_type")
    if current_user["role"] != "admin" and employment_type:
        if news["employment_type"] not in ["*", employment_type]:
            raise HTTPException(status_code=403, detail="Accesso non consentito")
    news["_id"] = str(news["_id"])
    if "author" in news and "_id" in news["author"]:
        news["author"]["_id"] = str(news["author"]["_id"])
    return request.app.state.templates.TemplateResponse(
        "ai_news.html",
        {
            "request": request,
            "user": current_user,
            "ai_news": [news],
            "new_doc_ids": [],
            "highlight_news_id": news_id
        }
    )