from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse, JSONResponse
from app.deps import require_admin, get_current_user
from app.utils.save_with_notifica import save_and_notify
from app.models.news_model import NewsIn, NewsOut
from datetime import datetime
from bson import ObjectId
from fastapi import status
from app.constants import DEFAULT_HIRE_TYPES
from app.notifiche import crea_notifica
from app.ws_broadcast import broadcast_message  # Aggiungi questa importazione

news_router = APIRouter(tags=["news"])

def get_news_toast(action, title):
    if action == "create":
        return {"message": f"È stata pubblicata una news: {title}", "type": "success"}
    elif action == "edit":
        return {"message": f"News modificata: {title}", "type": "info"}
    elif action == "delete":
        return {"message": f"News eliminata: {title}", "type": "danger"}

@news_router.post(
    "/news/new",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(require_admin)]
)
async def create_news(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    show_on_home: str = Form(None)
):
    print("[DEBUG] Inizio creazione news")
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    show_on_home_bool = bool(show_on_home)
    result = await save_and_notify(
        request=request,
        collection="news",
        payload={
            "title": title.strip(),
            "content": content.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "show_on_home": show_on_home_bool
        },
        tipo="news",
        titolo=title.strip(),
        branch=branch.strip()
    )
    db = request.app.state.db
    news = await db.news.find_one({"title": title.strip(), "content": content.strip()})
    print(f"[DEBUG] News creata: {news}")
    if show_on_home_bool and news:
        await db.home_highlights.update_one(
            {"type": "news", "object_id": news["_id"]},
            {"$set": {
                "type": "news",
                "object_id": news["_id"],
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
        print(f"[DEBUG] Aggiornata home_highlights per news {news['_id']}")
    elif news:
        await db.home_highlights.delete_one({"type": "news", "object_id": news["_id"]})
        print(f"[DEBUG] Rimossa home_highlights per news {news['_id']}")
    # Notifica via WebSocket (come per i link)
    try:
        import json
        notifica = await db.notifiche.find_one({"id_risorsa": str(news["_id"]), "tipo": "news"})
        print(f"[DEBUG] Notifica trovata: {notifica}")
        payload = {
            "type": "new_notification",
            "data": {
                "id": str(notifica["_id"]),
                "message": f"È stata pubblicata una news: {notifica.get('titolo', title.strip())}",
                "tipo": "news",
                "title": title.strip(),
                "branch": branch.strip()
            }
        }
        print(f"[DEBUG] Invio messaggio WebSocket: {payload}")
        await broadcast_message(json.dumps(payload))
        print("[DEBUG] Messaggio WebSocket inviato")
    except Exception as e:
        print("[WebSocket] Errore broadcast su new_notification news (create):", e)
    if request.headers.get("HX-Request"):
        response = request.app.state.templates.TemplateResponse(
            "news/news_row_partial.html",
            {"request": request, "n": news, "user": request.state.user}
        )
        response.headers["HX-Trigger"] = "closeModal"
        return response
    print("[DEBUG] Fine creazione news")
    return RedirectResponse("/news", status_code=303)

@news_router.get("/news", response_class=HTMLResponse)
async def list_news(
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    branch = current_user.get("branch")
    if current_user["role"] == "admin" or not employment_type:
        mongo_filter = {}
    else:
        mongo_filter = {
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
                        {"employment_type": "*"},
                        {"employment_type": {"$exists": False}}
                    ]
                }
            ]
        }
    news_items = await db.news.find(mongo_filter).sort("created_at", -1).to_list(None)

    # --- Segna tutte le notifiche 'news' come lette per l'utente ---
    def get_emp_type_conditions(user_emp_type):
        conds = [
            {"employment_type": {"$exists": False}},
            {"employment_type": []},
            {"employment_type": {"$in": ["*"]}}
        ]
        if user_emp_type:
            conds.append({"employment_type": {"$in": [user_emp_type]}})
        return conds

    user_id_str = str(current_user["_id"])
    notifications_to_mark_read_filter = {
        "tipo": "news",
        "branch": {"$in": ["*", branch]},
        "$or": get_emp_type_conditions(employment_type),
        "letta_da": {"$ne": user_id_str}
    }
    update_result = await db.notifiche.update_many(
        notifications_to_mark_read_filter,
        {"$addToSet": {"letta_da": user_id_str}}
    )

    # --- Conteggio notifiche non lette di tipo news per il badge ---
    unread_counts = {"news": await db.notifiche.count_documents({
        "tipo": "news",
        "letta_da": {"$ne": user_id_str},
        "branch": {"$in": ["*", branch]},
        "$or": get_emp_type_conditions(employment_type)
    })}

    response = request.app.state.templates.TemplateResponse(
        "news/news_index.html",
        {
            "request": request,
            "news": news_items,
            "current_user": current_user,
            "unread_counts": unread_counts,
        },
    )
    if update_result.modified_count > 0:
        import json
        triggers = {
            "refreshNotificheInlineEvent": "true",
            "refreshNewsBadgeEvent": "true"
        }
        response.headers["HX-Trigger"] = json.dumps(triggers)
    return response

@news_router.get(
    "/news/{news_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_news_form(
    request: Request,
    news_id: str,
    user = Depends(get_current_user)
):
    db = request.app.state.db
    news = await db.news.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(404, "News non trovata")
    return request.app.state.templates.TemplateResponse(
        "news/news_edit_partial.html",
        {"request": request, "n": news, "user": user}
    )

@news_router.post(
    "/news/{news_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_news_submit(
    request: Request,
    news_id: str,
    title: str = Form(...),
    content: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    show_on_home: str = Form(None)
):
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    show_on_home_bool = bool(show_on_home)
    await db.news.update_one(
        {"_id": ObjectId(news_id)},
        {"$set": {
            "title": title.strip(),
            "content": content.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "show_on_home": show_on_home_bool,
            "created_at": datetime.utcnow()
        }}
    )
    updated = await db.news.find_one({"_id": ObjectId(news_id)})
    if show_on_home_bool:
        await db.home_highlights.update_one(
            {"type": "news", "object_id": ObjectId(news_id)},
            {"$set": {
                "type": "news",
                "object_id": ObjectId(news_id),
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "news", "object_id": ObjectId(news_id)})
    resp = request.app.state.templates.TemplateResponse(
        "news/news_row_partial.html",
        {"request": request, "n": updated, "user": request.state.user}
    )
    resp.headers["HX-Trigger"] = "closeModal"
    # Elimino tutte le vecchie notifiche relative a questa news
    await db.notifiche.delete_many({"id_risorsa": str(news_id), "tipo": "news"})
    await crea_notifica(
        request=request,
        tipo="news",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=str(news_id),
        employment_type=employment_type_list
    )
    # Broadcast WebSocket per aggiornamento real-time dopo modifica
    try:
        import json
        payload = {
            "type": "update_news",
            "data": {
                "id": str(news_id),
                "title": title.strip(),
                "branch": branch.strip(),
                "consequence": "La news è stata modificata. I destinatari potrebbero essere cambiati."
            }
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su update_news:", e)
    return resp

@news_router.get("/news/new", response_class=HTMLResponse)
async def new_news(request: Request, current_user: dict = Depends(require_admin)):
    db = request.app.state.db
    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        hire_types = DEFAULT_HIRE_TYPES
    return request.app.state.templates.TemplateResponse(
        "news/news_new.html",
        {"request": request, "hire_types": hire_types}
    )

@news_router.delete("/news/{news_id}", status_code=200, dependencies=[Depends(require_admin)])
async def delete_news(request: Request, news_id: str, user=Depends(get_current_user)):
    db = request.app.state.db
    await db.news.delete_one({"_id": ObjectId(news_id)})
    await db.home_highlights.delete_one({"type": "news", "object_id": ObjectId(news_id)})
    # Broadcast WebSocket per aggiornamento real-time
    try:
        import json
        news = await db.news.find_one({"_id": ObjectId(news_id)})
        payload = {
            "type": "remove_news",
            "data": {
                "id": news_id,
                "title": news["title"] if news else None,
                "branch": news["branch"] if news else None
            }
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su remove_news:", e)
    return PlainTextResponse("")

@news_router.get('/news/partial', response_class=HTMLResponse)
async def news_partial(request: Request, current_user = Depends(get_current_user)):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    branch = current_user.get("branch")
    if current_user["role"] == "admin" or not employment_type:
        mongo_filter = {}
    else:
        mongo_filter = {
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
                        {"employment_type": "*"},
                        {"employment_type": {"$exists": False}}
                    ]
                }
            ]
        }
    news_items = await db.news.find(mongo_filter).sort("created_at", -1).to_list(None)
    print(f"[DEBUG] /news/partial: trovate {len(news_items)} news")
    response = request.app.state.templates.TemplateResponse(
        "partials/home_news_list.html",
        {"request": request, "news": news_items, "user": current_user}
    )
    return response

@news_router.get('/news/ticker', response_class=HTMLResponse)
async def news_ticker(request: Request, current_user = Depends(get_current_user)):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    branch = current_user.get("branch")
    if current_user["role"] == "admin" or not employment_type:
        mongo_filter = {}
    else:
        mongo_filter = {
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
                        {"employment_type": "*"},
                        {"employment_type": {"$exists": False}}
                    ]
                }
            ]
        }
    news_items = await db.news.find(mongo_filter).sort("created_at", -1).to_list(None)
    response = request.app.state.templates.TemplateResponse(
        "partials/news_ticker.html",
        {"request": request, "news": news_items, "user": current_user}
    )
    return response

@news_router.get("/news/{news_id}/row_partial", response_class=HTMLResponse)
async def news_row_partial(request: Request, news_id: str, user=Depends(get_current_user)):
    db = request.app.state.db
    news = await db.news.find_one({"_id": ObjectId(news_id)})
    return request.app.state.templates.TemplateResponse(
        "news/news_row_partial.html",
        {"request": request, "n": news, "user": user}
    )
