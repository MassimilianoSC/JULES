import json
from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File, Body
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, Response, PlainTextResponse
from app.deps import require_admin, get_current_user, get_docs_coll, get_db
from app.utils.save_with_notifica import save_and_notify
from bson import ObjectId
from datetime import datetime
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorCollection
import aiofiles
from mimetypes import guess_type
from app.notifiche import crea_notifica, crea_notifica_commento
from fastapi.templating import Jinja2Templates
from app.models.ai_news_model import AINewsBase, AINewsDB, CommentBase, CommentDB
from fastapi import Query
from app.ws_broadcast import broadcast_message
from typing import Optional
from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import core_schema
import bleach
import re
try:
    from markdown_it import MarkdownIt
except ImportError:
    MarkdownIt = None

# Costante per il percorso base dei documenti AI
BASE_AI_NEWS_DIR = Path("media/docs/ai_news")   # cartella radice documenti AI

def to_str_id(doc: dict) -> dict:
    """Converte l'_id Mongo in stringa per i template Jinja."""
    doc["_id"] = str(doc["_id"])
    if "uploaded_at" in doc and isinstance(doc["uploaded_at"], datetime):
        doc["uploaded_at"] = doc["uploaded_at"].date().isoformat()
    return doc

ai_news_router = APIRouter(tags=["ai_news"])

@ai_news_router.post(
    "/ai-news/upload",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(require_admin)]
)
async def upload_ai_news(
    request: Request,
    title: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    tags: str = Form(None),
    file: UploadFile = File(None),
    external_url: str = Form(None),
    show_on_home: str = Form(None),
    category: str = Form(...)
):
    show_on_home = show_on_home is not None

    # 1. Salva il file fisicamente (se presente)
    docs_dir = BASE_AI_NEWS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    filename = None
    content_type = None
    if file and file.filename:
        dest = docs_dir / file.filename
        async with aiofiles.open(dest, "wb") as out:
            await out.write(await file.read())
        filename = file.filename
        content_type = file.content_type

    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    # 2. Salva il documento in Mongo
    db = request.app.state.db
    doc = {
        "title": title.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list,
        "tags": [tag.strip() for tag in tags.split(",")] if tags else [],
        "filename": filename,
        "content_type": content_type,
        "external_url": external_url.strip() if external_url else None,
        "uploaded_at": datetime.utcnow(),
        "category": category.strip(),
        "stats": {
            "likes": 0,
            "comments": 0,
            "replies": 0,
            "total_interactions": 0
        }
    }
    # Se non c'è né file né link, errore
    if not filename and not external_url:
        from fastapi import RequestValidationError
        raise RequestValidationError([{"loc": ("file",), "msg": "Devi caricare un file o inserire un link esterno.", "type": "value_error"}])
    result = await db.ai_news.insert_one(doc)
    doc_id = result.inserted_id

    # 3. Aggiorna home_highlights
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "ai_news", "object_id": doc_id},
            {"$set": {
                "type": "ai_news",
                "object_id": doc_id,
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "ai_news", "object_id": doc_id})

    # 4. Crea la notifica
    await crea_notifica(
        request=request,
        tipo="ai_news",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=str(doc_id),
        employment_type=employment_type_list
    )
    print(f"[DEBUG AI_NEWS] Notifica creata per doc_id={doc_id}, employment_type={employment_type_list}")

    # 5. Invia WebSocket
    try:
        from app.ws_broadcast import broadcast_message
        # Toast verde e badge
        notifica = await db.notifiche.find_one({"id_risorsa": str(doc_id), "tipo": "ai_news"})
        print(f"[DEBUG AI_NEWS] notifica trovata dopo insert: {notifica}")
        if notifica:
            payload = {
                "type": "new_notification",
                "data": {
                    "id": str(notifica["_id"]),
                    "message": f"È stato pubblicato un nuovo documento AI: {title.strip()}",
                    "tipo": "ai_news"
                }
            }
            print(f"[DEBUG AI_NEWS] Invio payload WebSocket: {payload}")
            await broadcast_message(json.dumps(payload))
        # Aggiorna highlights home
        if show_on_home:
            payload_highlight = {
                "type": "update_ai_news_highlight",
                "data": {"id": str(doc_id)}
            }
            await broadcast_message(json.dumps(payload_highlight))
    except Exception as e:
        print("[WebSocket] Errore broadcast su creazione documento AI:", e)

    return RedirectResponse("/ai-news", status_code=303)

@ai_news_router.get("/ai-news/upload", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def show_upload_form(request: Request):
    branches = ["HQE", "HQ ITALIA", "HQIA"]
    types = ["TD", "TI", "AP", "CO"]
    return request.app.state.templates.TemplateResponse(
        "ai_news/upload.html",
        {"request": request, "branches": branches, "types": types}
    )

@ai_news_router.get(
    "/ai-news/{doc_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_ai_news_form(
    request: Request,
    doc_id: str,
    user = Depends(get_current_user)
):
    db = request.app.state.db
    doc = await db.ai_news.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Documento AI non trovato")
    # Verifica se il documento è in evidenza
    highlight = await db.home_highlights.find_one({"type": "ai_news", "object_id": ObjectId(doc_id)})
    doc = to_str_id(doc)
    doc["show_on_home"] = bool(highlight)
    return request.app.state.templates.TemplateResponse(
        "ai_news/edit_partial.html",
        {"request": request, "d": doc, "user": user}
    )

@ai_news_router.post(
    "/ai-news/{doc_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_ai_news_submit(
    request: Request,
    doc_id: str,
    title: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    tags: str = Form(None),
    category: str = Form(...),
    show_on_home: str = Form(None)
):
    print("[DEBUG] show_on_home =", show_on_home)
    show_on_home = show_on_home is not None
    print("[DEBUG] Prima del controllo show_on_home, valore:", show_on_home)
    if show_on_home:
        print("[DEBUG] Entro nel ramo show_on_home True")
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    await db.ai_news.update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": {
            "title": title.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "tags": [tag.strip() for tag in tags.split(",")] if tags else [],
            "category": category.strip()
        }}
    )

    # Gestione home_highlights
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "ai_news", "object_id": ObjectId(doc_id)},
            {"$set": {
                "type": "ai_news",
                "object_id": ObjectId(doc_id),
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "ai_news", "object_id": ObjectId(doc_id)})

    # Dopo l'update, crea una nuova notifica per i nuovi destinatari
    await crea_notifica(
        request=request,
        tipo="ai_news",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=str(doc_id),
        employment_type=employment_type_list
    )
    # Invia WebSocket
    try:
        from app.ws_broadcast import broadcast_message
        # Aggiorna lista documenti
        payload_update = {
            "type": "update_ai_news",
            "data": {
                "id": str(doc_id),
                "titolo": title.strip(),
                "branch": branch.strip(),
                "consequence": "Il documento AI è stato modificato. I destinatari potrebbero essere cambiati."
            }
        }
        await broadcast_message(json.dumps(payload_update))
        # Aggiorna highlights home SOLO se show_on_home
        if show_on_home:
            payload_highlight = {
                "type": "update_ai_news_highlight",
                "data": {"id": str(doc_id)}
            }
            await broadcast_message(json.dumps(payload_highlight))
        # Toast giallo e badge (a tutti)
        notifica = await db.notifiche.find_one({"id_risorsa": str(doc_id), "tipo": "ai_news"})
        if notifica:
            payload_toast = {
                "type": "new_notification",
                "data": {
                    "id": str(notifica["_id"]),
                    "message": f"Documento AI modificato: {title.strip()}",
                    "tipo": "ai_news"
                }
            }
            await broadcast_message(json.dumps(payload_toast))
    except Exception as e:
        print("[WebSocket] Errore broadcast su modifica documento AI:", e)
    updated = await db.ai_news.find_one({"_id": ObjectId(doc_id)})
    resp = request.app.state.templates.TemplateResponse(
        "ai_news/row_partial.html",
        {"request": request, "d": updated, "user": request.state.user}
    )
    resp.headers["HX-Trigger"] = "closeModal"
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

@ai_news_router.delete("/ai-news/{doc_id}")
async def delete_ai_news(request: Request, doc_id: str):
    db = request.app.state.db
    # Recupera info documento prima di eliminare
    doc = await db.ai_news.find_one({"_id": ObjectId(doc_id)})
    title = doc["title"] if doc else ""
    await db.ai_news.delete_one({"_id": ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id})
    # rimuovi eventuale highlight
    try:
        obj_id = ObjectId(doc_id)
    except Exception:
        obj_id = doc_id
    await db.home_highlights.delete_many({
        "type": "ai_news",
        "$or": [
            {"object_id": obj_id},
            {"object_id": str(doc_id)}
        ]
    })
    # Invia WebSocket
    # Invia WebSocket
    try:
        from app.ws_broadcast import broadcast_message
        # Aggiorna lista documenti
        payload_remove = {
            "type": "remove_ai_news",
            "data": {
                "id": str(doc_id),
                "user_id": str(request.state.user['_id'])
            }
        }
        await broadcast_message(json.dumps(payload_remove))
        # Aggiorna highlights home
        payload_highlight = {
            "type": "update_ai_news_highlight",
            "data": {"id": str(doc_id)}
        }
        await broadcast_message(json.dumps(payload_highlight))
        # Toast rosso e badge (a tutti)
        payload_toast = {
            "type": "new_notification",
            "data": {
                "id": str(doc_id),
                "message": f"Documento AI eliminato: {title}",
                "tipo": "ai_news"
            }
        }
        await broadcast_message(json.dumps(payload_toast))
    except Exception as e:
        print("[WebSocket] Errore broadcast su eliminazione documento AI:", e)
    return Response(status_code=200, media_type="text/plain")

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

@ai_news_router.post("/api/ai-news/{news_id}/view")
async def track_ai_news_view(
    news_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    view_doc = {
        "news_id": ObjectId(news_id),
        "user_id": ObjectId(current_user["_id"]),
        "timestamp": datetime.utcnow(),
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent", "")
    }
    await db.ai_news_views.insert_one(view_doc)
    await db.ai_news.update_one(
        {"_id": ObjectId(news_id)},
        {"$inc": {"stats.views": 1}}
    )
    # Invia messaggio WebSocket come JSON
    await broadcast_message(json.dumps({
        "type": "stats:ai_news",
        "data": {"news_id": str(news_id), "action": "view"}
    }))
    return {"success": True}

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
async def get_ai_news_stats(
    news_id: str,
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    news = await db.ai_news.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(status_code=404, detail="News non trovata")
    user_like = await db.ai_news_likes.find_one({
        "news_id": ObjectId(news_id),
        "user_id": ObjectId(current_user["_id"])
    })
    return {
        "stats": news.get("stats", {"views": 0, "likes": 0, "comments": 0}),
        "user_liked": bool(user_like)
    }

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

@ai_news_router.post("/api/ai-news/{news_id}/comments")
async def add_comment(
    news_id: str,
    request: Request,
    content: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    comment: Optional[CommentBase] = Body(None),
    user = Depends(get_current_user)
):
    try:
        if comment and comment.content:
            comment_data = comment.dict()
            # Pulizia spazi bianchi dal contenuto
            comment_data["content"] = comment_data["content"].strip()
        elif content:
            comment_data = {
                "content": content.strip(),  # Pulizia spazi bianchi
                "parent_id": parent_id
            }
        else:
            raise HTTPException(422, "Content richiesto")

        db = request.app.state.db
        # Validazione degli ID
        try:
            news_id_obj = ObjectId(news_id)
            user_id_obj = ObjectId(user["_id"])
            parent_id_obj = ObjectId(comment_data["parent_id"]) if comment_data.get("parent_id") else None
        except Exception as e:
            raise HTTPException(400, f"ID non valido: {str(e)}")

        # Verifica esistenza news
        news = await db.ai_news.find_one({"_id": news_id_obj})
        if not news:
            raise HTTPException(404, "News non trovata")

        # Verifica esistenza commento padre se presente
        if parent_id_obj:
            parent = await db.ai_news_comments.find_one({"_id": parent_id_obj})
            if not parent:
                raise HTTPException(404, "Commento padre non trovato")

        # Crea il commento
        comment_doc = {
            "news_id": news_id_obj,
            "author_id": user_id_obj,
            "content": comment_data["content"],
            "parent_id": parent_id_obj,
            "created_at": datetime.utcnow(),
            "likes": 0,
            "replies_count": 0
        }
        result = await db.ai_news_comments.insert_one(comment_doc)
        comment_id = str(result.inserted_id)

        # Aggiorna il contatore dei commenti della news
        await db.ai_news.update_one(
            {"_id": news_id_obj},
            {"$inc": {"stats.comments": 1}}
        )

        # Se è una risposta, aggiorna il contatore delle risposte del commento padre
        if parent_id_obj:
            await db.ai_news_comments.update_one(
                {"_id": parent_id_obj},
                {"$inc": {"replies_count": 1}}
            )

        # Crea notifiche per gli utenti non connessi
        try:
            await crea_notifica_commento(
                request=request,
                news_id=news_id,
                comment_id=comment_id,
                author_id=str(user_id_obj),
                parent_id=str(parent_id_obj) if parent_id_obj else None,
                mentioned_users=comment_data.get("mentions", [])
            )
        except Exception as e:
            print(f"[ERROR] Errore nella creazione delle notifiche: {str(e)}")

        # Invia notifica real-time tramite WebSocket
        try:
            from app.ws_broadcast import broadcast_message
            await broadcast_message(json.dumps({
                "type": "comment:ai_news",
                "data": {
                    "ai_news_id": str(news_id),
                    "comment_id": str(comment_id),
                    "author_id": str(user["_id"]),
                    "action": "create"
                }
            }))
        except Exception as e:
            print(f"[ERROR] Errore nell'invio della notifica WebSocket: {str(e)}")

        return {"id": comment_id}

    except Exception as e:
        print(f"[ERROR] Errore nella creazione del commento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
    if str(comment["author_id"]) != str(current_user["_id"]) and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Non autorizzato")
    await db.ai_news_comments.delete_one({"_id": ObjectId(comment_id)})
    await db.ai_news.update_one(
        {"_id": comment["news_id"]},
        {"$inc": {"stats.comments": -1}}
    )
    if comment.get("parent_id"):
        await db.ai_news_comments.update_one(
            {"_id": comment["parent_id"]},
            {"$inc": {"replies_count": -1}}
        )
    await broadcast_message(json.dumps({
        "type": "comment:ai_news",
        "data": {
            "ai_news_id": str(comment["news_id"]),
            "comment_id": str(comment["_id"]),
            "action": "delete"
        }
    }))
    return {"success": True}

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
    updated = await db.ai_news_comments.find_one({"_id": ObjectId(comment_id)})
    await broadcast_message(json.dumps({
        "type": "comment:ai_news",
        "data": {
            "ai_news_id": str(comment["news_id"]),
            "comment_id": str(comment["_id"]),
            "action": "like"
        }
    }))
    return {"liked": inc_value > 0, "likes": updated.get("likes", 0)}

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
    update_data = {
        "content": comment_update.content,
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
        {"$inc": {"replies_count": -1}}
    )
    await broadcast_message(json.dumps({
        "type": "comment:ai_news",
        "data": {
            "ai_news_id": str(reply["news_id"]),
            "comment_id": str(reply["_id"]),
            "action": "delete"
        }
    }))
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