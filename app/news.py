from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse, JSONResponse
from app.deps import require_admin, get_current_user
from app.utils.save_with_notifica import save_and_notify
from app.models.news_model import NewsIn, NewsOut
from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import status
from app.constants import DEFAULT_HIRE_TYPES
from app.notifiche import crea_notifica
from app.ws_broadcast import broadcast_message, broadcast_resource_event
from app.utils.notification_helpers import create_action_notification_payload, create_admin_confirmation_trigger
import json

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
    response_class=Response,
    dependencies=[Depends(require_admin)]
)
async def create_news(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    show_on_home: str = Form(None),
    priority: int = Form(3), # Aggiunto priority
    expires_at_str: str = Form(None), # Aggiunto expires_at_str
    current_user: dict = Depends(get_current_user)
):
    print("[DEBUG] Inizio creazione news")
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    show_on_home = show_on_home is not None

    expires_at = None
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
        except ValueError:
            pass # Lascia expires_at = None se il formato non è valido

    # Salva la news nel DB
    db = request.app.state.db
    news_data = {
        "title": title.strip(),
        "content": content.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list,
        "created_at": datetime.utcnow(),
        "show_on_home": show_on_home,
        "priority": priority, # Aggiunto al salvataggio
        "expires_at": expires_at # Aggiunto al salvataggio
    }
    result = await db.news.insert_one(news_data)
    news_id = str(result.inserted_id)

    # Crea la notifica
    await crea_notifica(
        request=request,
        tipo="news",
        titolo=title.strip(),
        branch=branch.strip(),
        id_risorsa=news_id,
        employment_type=employment_type_list
    )

    # 1. Notifica WebSocket ai destinatari, ESCLUDENDO l'admin che ha creato la news
    payload = create_action_notification_payload('create', 'news', title.strip(), str(current_user["_id"]))
    await broadcast_message(
        payload,
        branch=branch.strip(),
        employment_type=employment_type_list,
        exclude_user_id=str(current_user["_id"])
    )

    # 2. Aggiornamento highlights (se necessario) - RIMOSSO perché le news non vanno più in home_highlights come card
    # if show_on_home:
    #     await db.home_highlights.insert_one({
    #         "type": "news",
    #         "object_id": news_id,
    #         "title": title.strip(),
    #         "created_at": datetime.utcnow(),
    #         "branch": branch.strip(), # branch della news
    #         "employment_type": employment_type_list # employment_type della news
    #     })
    #     # Invia broadcast mirato per refresh_home_highlights - RIMOSSO
    #     try:
    #         payload_highlight = {
    #             "type": "refresh_home_highlights",
    #             "data": {
    #                 "branch": branch.strip(),
    #                 "employment_type": employment_type_list
    #             }
    #         }
    #         await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type_list)
    #     except Exception as e:
    #         print(f"[WebSocket] Errore broadcast refresh_home_highlights (create news): {e}")

        # Invia anche l'evento generico di aggiunta risorsa - MANTENUTO se serve per altri aggiornamenti UI (es. lista /news)
    await broadcast_resource_event("add", item_type="news", item_id=news_id, user_id=str(current_user["_id"]))

    # 3. Risposta con conferma admin e redirect
    resp = Response(status_code=200)
    # Prima mostra la conferma
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', title.strip())
    # Poi chiudi la modale e fai il redirect
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirect-to-news": "/news"
    })
    return resp

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
    show_on_home: str = Form(None),
    priority: int = Form(None), # Aggiunto priority opzionale
    expires_at_str: str = Form(None), # Aggiunto expires_at_str opzionale
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    show_on_home_bool = bool(show_on_home)

    update_fields = {
        "title": title.strip(),
        "content": content.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type_list,
        "show_on_home": show_on_home_bool,
        # Non aggiorniamo created_at durante una modifica, ma piuttosto updated_at se lo avessimo
    }

    if priority is not None:
        update_fields["priority"] = priority

    if expires_at_str is not None:
        if not expires_at_str: # Stringa vuota per rimuovere la data
            update_fields["expires_at"] = None
        else:
            try:
                update_fields["expires_at"] = datetime.fromisoformat(expires_at_str)
            except ValueError:
                # Opzione: ignorare la data malformata o sollevare un errore?
                # Per ora la ignoro, non aggiornando il campo.
                pass

    if update_fields: # Solo se ci sono campi da aggiornare (dovrebbe sempre esserci almeno il titolo)
        await db.news.update_one(
            {"_id": ObjectId(news_id)},
            {"$set": update_fields}
        )

    updated = await db.news.find_one({"_id": ObjectId(news_id)})
    # RIMOSSA logica di interazione con db.home_highlights per le news
    # if show_on_home_bool:
    #     await db.home_highlights.update_one(
    #         {"type": "news", "object_id": ObjectId(news_id)},
    #         {"$set": {
    #             "type": "news",
    #             "object_id": ObjectId(news_id),
    #             "title": title.strip(),
    #             "created_at": datetime.utcnow(),
    #             "branch": branch.strip(),
    #             "employment_type": employment_type_list
    #         }},
    #         upsert=True
    #     )
    # else:
    #     await db.home_highlights.delete_one({"type": "news", "object_id": ObjectId(news_id)})
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
    # 1. Notifica WebSocket ai destinatari, ESCLUDENDO l'admin che ha modificato la news
    payload = create_action_notification_payload('update', 'news', title.strip(), str(current_user["_id"]))
    await broadcast_message(
        payload,
        branch=branch.strip(),
        employment_type=employment_type_list,
        exclude_user_id=str(current_user["_id"])
    )
    # 2. Aggiornamento highlights - RIMOSSA logica broadcast refresh_home_highlights per le news
    # if show_on_home_bool:
    #     try:
    #         payload_highlight = {
    #             "type": "refresh_home_highlights",
    #             "data": {
    #                 "branch": branch.strip(),
    #                 "employment_type": employment_type_list
    #             }
    #         }
    #         await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type_list)
    #     except Exception as e:
    #         print(f"[WebSocket] Errore broadcast refresh_home_highlights (edit news - show_on_home): {e}")
    # elif not show_on_home_bool:
    #     try:
    #         payload_highlight = {
    #             "type": "refresh_home_highlights",
    #             "data": {
    #                 "branch": branch.strip(),
    #                 "employment_type": employment_type_list
    #             }
    #         }
    #         await broadcast_message(payload_highlight, branch=branch.strip(), employment_type=employment_type_list)
    #         print(f"[DEBUG] News non più show_on_home, inviato refresh_home_highlights per la rimozione.")
    #     except Exception as e:
    #         print(f"[WebSocket] Errore broadcast refresh_home_highlights (edit news - not show_on_home): {e}")

    await broadcast_resource_event("update", item_type="news", item_id=news_id, user_id=str(current_user["_id"]))
    # --- FINE AGGIUNTA ---

    # Toast di notifica
    payload_toast = {
        "type": "new_notification",
        "data": {
            "id": str(news_id),
            "message": f"È stata aggiunta una nuova news: {title.strip()}",
            "tipo": "news",
            "source_user_id": str(current_user["_id"])
        }
    }
    await broadcast_message(payload_toast, branch=branch, employment_type=employment_type_list, exclude_user_id=str(current_user["_id"]))

    # Risposta con conferma admin e redirect
    resp = Response(status_code=204)
    # Prima mostra la conferma
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', title.strip())
    # Poi chiudi la modale e fai il redirect
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirect-to-news": "/news"
    })
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
async def delete_news(request: Request, news_id: str, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    news = await db.news.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(status_code=404, detail="News non trovata")
    
    # Elimina la news dal DB
    await db.news.delete_one({"_id": ObjectId(news_id)})
    
    # 1. Notifica WebSocket ai destinatari (tutti tranne l'admin)
    payload = create_action_notification_payload('delete', 'news', news.get('title', ''), str(current_user["_id"]))
    await broadcast_message(
        payload,
        branch=news.get("branch", "*"), # Usa il branch della news per la notifica di eliminazione
        employment_type=news.get("employment_type", ["*"]), # Usa l'emp_type della news
        exclude_user_id=str(current_user["_id"])
    )
    
    # 2. Aggiornamento highlights e card fissa in home
    # Rimuovi da home_highlights
    await db.home_highlights.delete_one({"type": "news", "object_id": ObjectId(news_id)}) # Assicuriamoci che venga rimosso

    # RIMOSSA logica broadcast refresh_home_highlights per le news
    # was_on_home = news.get("show_on_home", False)
    # if was_on_home:
    #     try:
    #         payload_highlight = {
    #             "type": "refresh_home_highlights",
    #             "data": {
    #                 "branch": news.get("branch", "*"),
    #                 "employment_type": news.get("employment_type", ["*"])
    #             }
    #         }
    #         await broadcast_message(
    #             payload_highlight,
    #             branch=news.get("branch", "*"),
    #             employment_type=news.get("employment_type", ["*"])
    #         )
    #     except Exception as e:
    #         print(f"[WebSocket] Errore broadcast refresh_home_highlights (delete news): {e}")

    await broadcast_resource_event("delete", item_type="news", item_id=news_id, user_id=str(current_user["_id"]))
    
    # 3. Conferma per l'admin
    resp = Response(status_code=200)
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('delete', news.get('title', ''))
    return resp

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

# @news_router.post("/new", dependencies=[Depends(require_admin)])
# async def create_news(
#     request: Request,
#     title: str = Form(...),
#     content: str = Form(...),
#     priority: int = Form(3),
#     expires_at_str: str = Form(None),
#     current_user: dict = Depends(get_current_user)
# ):
#     db = request.app.state.db
    
#     expires_at = None
#     if expires_at_str:
#         try:
#             expires_at = datetime.fromisoformat(expires_at_str)
#         except ValueError:
#             pass

#     news_data = {
#         "title": title.strip(), "content": content.strip(), "branch": "*",
#         "employment_type": ["*"], "priority": priority, "pinned": False,
#         "expires_at": expires_at, "created_at": datetime.utcnow()
#     }
#     result = await db.news.insert_one(news_data)
    
#     # L'ID della nuova news viene salvato qui. Questa è la variabile da usare.
#     new_id = str(result.inserted_id)

#     # 1. Notifica WebSocket ai destinatari
#     payload = create_action_notification_payload('create', 'news', title, str(current_user["_id"]))
#     await broadcast_message(payload, exclude_user_id=str(current_user["_id"]))

#     # --- CORREZIONE DEFINITIVA ---
#     # Il problema era nella riga seguente.
#     # Usiamo la variabile `new_id` che abbiamo appena ottenuto,
#     # invece di una variabile `news` inesistente.
#     await broadcast_resource_event("add", item_type="news", item_id=new_id, user_id=str(current_user["_id"]))
    
#     # Aggiungi a home_highlights (ora che l'evento broadcast è corretto)
#     # Questa news sembra essere globale ("branch": "*", "employment_type": ["*"])
#     # Quindi il broadcast di refresh_home_highlights dovrebbe essere per tutti se è show_on_home
#     # Tuttavia, la news creata qui non ha un campo show_on_home esplicito,
#     # si assume che vada sempre in home_highlights.
    
#     news_doc_for_highlight = {
#         "type": "news", "object_id": new_id, "title": title,
#         "branch": "*", "employment_type": ["*"], "created_at": datetime.utcnow()
#     }
#     await db.home_highlights.insert_one(news_doc_for_highlight)

#     # Assumendo che questa news vada sempre in home, inviamo il refresh.
#     # Poiché branch/emp_type sono "*", il broadcast sarà effettivamente per tutti.
#     try:
#         payload_highlight = {
#             "type": "refresh_home_highlights",
#             "data": {
#                 "branch": "*", # Dalla logica di questa funzione
#                 "employment_type": ["*"] # Dalla logica di questa funzione
#             }
#         }
#         await broadcast_message(payload_highlight, branch="*", employment_type=["*"])
#     except Exception as e:
#         print(f"[WebSocket] Errore broadcast refresh_home_highlights (create news global): {e}")

#     # 3. Conferma per l'admin
#     resp = Response(status_code=200)
#     resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', title)
#     return resp

# @news_router.post("/{news_id}/edit", dependencies=[Depends(require_admin)])
# async def edit_news_submit_global(
#     request: Request, news_id: str,
#     title: str = Form(...),
#     content: str = Form(...),
#     priority: int = Form(3),
#     expires_at_str: str = Form(None),
#     current_user: dict = Depends(get_current_user)
# ):
#     db = request.app.state.db
    
#     expires_at = None
#     if expires_at_str:
#         try:
#             expires_at = datetime.fromisoformat(expires_at_str)
#         except ValueError:
#             pass

#     await db.news.update_one(
#         {"_id": ObjectId(news_id)},
#         {"$set": {
#             "title": title.strip(),
#             "content": content.strip(),
#             "priority": priority,
#             "expires_at": expires_at
#         }}
#     )

#     # 1. Notifica WebSocket a TUTTI (escludendo l'admin)
#     payload = create_action_notification_payload('update', 'news', title, str(current_user["_id"]))
#     await broadcast_message(payload, exclude_user_id=str(current_user["_id"]))

#     # 2. Aggiorna highlights e notifica per l'aggiornamento UI
#     await db.home_highlights.update_one({"object_id": news_id}, {"$set": {"title": title}})
#     await broadcast_resource_event("update", item_type="news", item_id=news_id, user_id=str(current_user["_id"]))

#     # 3. Conferma immediata SOLO per l'admin
#     updated_news = await db.news.find_one({"_id": ObjectId(news_id)})
#     resp = request.app.state.templates.TemplateResponse(
#         "news/news_row_partial.html", {"request": request, "n": updated_news, "user": current_user}
#     )
#     resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('update', title)
#     return resp

# @news_router.delete("/{news_id}", dependencies=[Depends(require_admin)])
# async def delete_news_global(
#     request: Request, news_id: str, current_user: dict = Depends(get_current_user)
# ):
#     db = request.app.state.db
#     news_to_delete = await db.news.find_one({"_id": ObjectId(news_id)})
#     if not news_to_delete:
#         raise HTTPException(status_code=404)
    
#     title = news_to_delete['title']
#     await db.news.delete_one({"_id": ObjectId(news_id)})

#     # 1. Notifica WebSocket a TUTTI (escludendo l'admin)
#     payload = create_action_notification_payload('delete', 'news', title, str(current_user["_id"]))
#     await broadcast_message(payload, exclude_user_id=str(current_user["_id"]))

#     # 2. Rimuovi da highlights e notifica per l'aggiornamento UI
#     await db.home_highlights.delete_one({"type": "news", "object_id": news_id}) # Specificare type

#     # Poiché questa news è globale (branch: "*", employment_type: ["*"]),
#     # il refresh dovrebbe essere inviato a tutti se la news era in home_highlights.
#     # Non c'è un campo show_on_home esplicito qui, si assume che se è in home_highlights, era mostrata.
#     # La rimozione da db.home_highlights è già avvenuta.
#     # Se vogliamo inviare il refresh solo se era effettivamente lì, dovremmo sapere se delete_one ha avuto successo.
#     # Per ora, inviamo il refresh assumendo che potesse essere lì.
#     try:
#         payload_highlight = {
#             "type": "refresh_home_highlights",
#             "data": {
#                 "branch": "*", # Dalla logica di questa funzione
#                 "employment_type": ["*"] # Dalla logica di questa funzione
#             }
#         }
#         await broadcast_message(payload_highlight, branch="*", employment_type=["*"])
#     except Exception as e:
#         print(f"[WebSocket] Errore broadcast refresh_home_highlights (delete news global): {e}")

#     await broadcast_resource_event("delete", item_type="news", item_id=news_id, user_id=str(current_user["_id"]))

#     # 3. Conferma immediata SOLO per l'admin
#     resp = Response(status_code=200)
#     resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('delete', title)
#     return resp

@news_router.post("/{news_id}/pin", dependencies=[Depends(require_admin)])
async def pin_news(request: Request, news_id: str, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    
    # Imposta `pinned` a True e aggiunge un timestamp per l'ordinamento
    await db.news.update_one(
        {"_id": ObjectId(news_id)},
        {"$set": {"pinned": True, "pinned_at": datetime.utcnow()}}
    )
    
    news_item = await db.news.find_one({"_id": ObjectId(news_id)})
    title = news_item.get("title", "News")

    # Notifica e aggiornamento UI per tutti
    payload = create_action_notification_payload('update', 'news', f"Fissata: {title}", str(current_user["_id"]))
    await broadcast_message(payload, exclude_user_id=str(current_user["_id"]))
    await broadcast_resource_event("update", item_type="news", item_id=news_id, user_id=str(current_user["_id"]))

    # Restituisce il partial aggiornato per la singola riga della news
    updated_news = await db.news.find_one({"_id": ObjectId(news_id)})
    return request.app.state.templates.TemplateResponse(
        "news/news_row_partial.html", {"request": request, "n": updated_news, "user": current_user}
    )

@news_router.post("/{news_id}/unpin", dependencies=[Depends(require_admin)])
async def unpin_news(request: Request, news_id: str, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    
    # Imposta `pinned` a False e rimuove il timestamp
    await db.news.update_one(
        {"_id": ObjectId(news_id)},
        {"$set": {"pinned": False}, "$unset": {"pinned_at": ""}}
    )
    
    news_item = await db.news.find_one({"_id": ObjectId(news_id)})
    title = news_item.get("title", "News")

    # Notifica e aggiornamento UI
    payload = create_action_notification_payload('update', 'news', f"Rimossa dagli elementi fissati: {title}", str(current_user["_id"]))
    await broadcast_message(payload, exclude_user_id=str(current_user["_id"]))
    await broadcast_resource_event("update", item_type="news", item_id=news_id, user_id=str(current_user["_id"]))

    # Restituisce il partial aggiornato
    updated_news = await db.news.find_one({"_id": ObjectId(news_id)})
    return request.app.state.templates.TemplateResponse(
        "news/news_row_partial.html", {"request": request, "n": updated_news, "user": current_user}
    )
