from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from app.deps import require_admin, get_current_user
from bson import ObjectId
from datetime import datetime
import json

from app.utils.notification_helpers import create_action_notification_payload, create_admin_confirmation_trigger
from app.ws_broadcast import broadcast_message, broadcast_resource_event

# Aggiunto il prefisso "/links" per allineare le rotte con il frontend
links_router = APIRouter(prefix="/links", tags=["links"])

@links_router.post("/new", dependencies=[Depends(require_admin)])
async def create_link(
    request: Request, 
    title: str = Form(...), 
    url: str = Form(...), 
    branch: str = Form("*"), 
    employment_type: list[str] = Form(["*"]), 
    show_on_home: bool = Form(False), 
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    
    # Crea il link nel DB
    link_data = {
        "title": title.strip(),
        "url": url.strip(),
        "branch": branch.strip(),
        "employment_type": employment_type,
        "show_on_home": show_on_home,
        "created_at": datetime.utcnow()
    }
    result = await db.links.insert_one(link_data)
    new_id = str(result.inserted_id)

    # 1. Notifica WebSocket SOLO ai destinatari
    payload = create_action_notification_payload(
        'create',
        'link',
        title.strip(),
        str(current_user["_id"])
    )
    await broadcast_message(
        payload, 
        branch=branch, 
        employment_type=employment_type,  # Passa la lista direttamente
        exclude_user_id=str(current_user["_id"])
    )

    # 2. Broadcast dell'evento per aggiornare UI
    await broadcast_resource_event(
        event="add",
        item_type="link",
        item_id=new_id,
        user_id=str(current_user["_id"]),
    )

    # 3. Aggiornamento highlights (se necessario)
    if show_on_home:
        await db.home_highlights.insert_one({
            "type": "link",
            "object_id": new_id,
            "title": title,
            "url": url,
            "branch": branch,
            "employment_type": employment_type,
            "created_at": datetime.utcnow()
        })
        # Aggiorna highlights home
        try:
            print(f"[DEBUG] Aggiornamento highlights")
            payload_highlight = {
                "type": "refresh_home_highlights"
            }
            await broadcast_message(payload_highlight)
            print(f"[DEBUG] Highlights aggiornati")
        except Exception as e:
            print("[WebSocket] Errore broadcast su refresh highlights:", e)

    # 4. Risposta di conferma per l'admin con redirect ritardato
    print(f"[DEBUG] Preparazione risposta")
    resp = Response(status_code=200)
    # Prima mostra la conferma
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', title)
    # Poi chiudi la modale e fai il redirect
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirect-to-links": "/links"
    })
    print(f"[DEBUG] Headers risposta: {dict(resp.headers)}")
    return resp

@links_router.get("/", response_class=HTMLResponse)
async def list_links(request: Request, current_user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    branch = current_user.get("branch")
    print(f"[DEBUG] Utente corrente: {current_user}")
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
                        {"employment_type": {"$elemMatch": {"$in": [employment_type, "*"]}}},
                        {"employment_type": {"$exists": False}},
                        {"employment_type": []}
                    ]
                }
            ]
        }
    print(f"[DEBUG] Filtro Mongo: {mongo_filter}")
    links = await db.links.find(mongo_filter).to_list(length=None)
    print(f"[DEBUG] Link trovati: {[l.get('title') for l in links]}")

    # --- Segna tutte le notifiche 'link' come lette per l'utente ---
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
        "tipo": "link",
        "branch": {"$in": ["*", branch]},
        "$or": get_emp_type_conditions(employment_type),
        "letta_da": {"$ne": user_id_str}
    }
    update_result = await db.notifiche.update_many(
        notifications_to_mark_read_filter,
        {"$addToSet": {"letta_da": user_id_str}}
    )
    print(f"[DEBUG] Segnate {update_result.modified_count} notifiche link come lette per {user_id_str} visitando /links")

    # --- Conteggio notifiche non lette di tipo link per il badge ---
    unread_counts = {"link": await db.notifiche.count_documents({
        "tipo": "link",
        "letta_da": {"$ne": user_id_str},
        "branch": {"$in": ["*", branch]},
        "$or": get_emp_type_conditions(employment_type)
    })}

    response = request.app.state.templates.TemplateResponse(
        "links/links_index.html",
        {
            "request": request,
            "links": links,
            "current_user": current_user,
            "unread_counts": unread_counts,
        },
    )
    if update_result.modified_count > 0:
        import json
        triggers = {
            "refreshNotificheInlineEvent": "true",
            "refreshLinkBadgeEvent": "true"
        }
        response.headers["HX-Trigger"] = json.dumps(triggers)
    return response

@links_router.get(
    "/{link_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_link_form(
    request: Request,
    link_id: str,
    user = Depends(get_current_user)
):
    db = request.app.state.db
    link = await db.links.find_one({"_id": ObjectId(link_id)})
    if not link:
        raise HTTPException(404, "Link non trovato")
    branches = ["*", "HQE", "HQ ITALIA", "HQIA"]
    employment_types = ["*", "TD", "TI", "AP", "CO"]
    is_htmx = request.headers.get("hx-request") == "true"
    template = "links/links_edit_partial.html" if is_htmx else "links/links_edit.html"
    return request.app.state.templates.TemplateResponse(
        template,
        {
            "request": request,
            "l": link,
            "branches": branches,
            "employment_types": employment_types,
            "branch": link.get("branch", "*"),
            "employment_type": (link.get("employment_type", ["*"])[0] if isinstance(link.get("employment_type", ["*"]), list) else link.get("employment_type", ["*"])),
            "show_on_home": link.get("show_on_home", False),
            "current_user": user,
        }
    )

@links_router.delete("/{link_id}", dependencies=[Depends(require_admin)])
async def delete_link(request: Request, link_id: str, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    
    # Verifica che l'ID sia valido e che il link esista prima di procedere.
    try:
        object_id_to_delete = ObjectId(link_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID del link non valido.")
        
    link_to_delete = await db.links.find_one({"_id": object_id_to_delete})
    if not link_to_delete:
        # Se il link non viene trovato nel DB, si solleva un 404.
        # Questo è il comportamento corretto.
        raise HTTPException(status_code=404, detail="Link non trovato.")
    
    title = link_to_delete.get('title', 'Link sconosciuto')
    branch = link_to_delete.get('branch', '*')
    employment_type = link_to_delete.get('employment_type', ['*'])

    # Esegui l'eliminazione
    await db.links.delete_one({"_id": object_id_to_delete})
    
    # 1. Notifica WebSocket SOLO ai destinatari
    payload = create_action_notification_payload(
        'delete',
        'link',
        title,
        str(current_user["_id"])
    )
    await broadcast_message(
        payload, 
        branch=branch, 
        employment_type=employment_type,  # Passa la lista direttamente
        exclude_user_id=str(current_user["_id"])
    )

    # 2. Aggiornamento highlights
    await db.home_highlights.delete_one({"object_id": link_id})
    await broadcast_resource_event(
        event="delete",
        item_type="link",
        item_id=link_id,
        user_id=str(current_user["_id"])
    )

    # 3. Conferma immediata SOLO per l'admin
    resp = Response(status_code=200)
    admin_trigger = create_admin_confirmation_trigger('delete', title)
    print("[DEBUG-LINKS-DELETE] Payload conferma admin:", admin_trigger)
    resp.headers["HX-Trigger"] = admin_trigger
    return resp

@links_router.post("/{link_id}/edit", dependencies=[Depends(require_admin)])
async def edit_link_submit(
    request: Request, 
    link_id: str, 
    title: str = Form(...), 
    url: str = Form(...), 
    branch: str = Form(...), 
    employment_type: list[str] = Form(...), 
    show_on_home: bool = Form(False), 
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    await db.links.update_one(
        {"_id": ObjectId(link_id)}, 
        {"$set": {
            "title": title.strip(),
            "url": url.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type,
            "show_on_home": show_on_home
        }}
    )

    # 1. Notifica WebSocket SOLO ai destinatari
    payload = create_action_notification_payload(
        'update',
        'link',
        title.strip(),
        str(current_user["_id"])
    )
    await broadcast_message(
        payload, 
        branch=branch, 
        employment_type=employment_type,  # Passa la lista direttamente
        exclude_user_id=str(current_user["_id"])
    )

    # 2. Aggiornamento highlights
    await broadcast_resource_event(
        event="update",
        item_type="link",
        item_id=link_id,
        user_id=str(current_user["_id"])
    )

    # 3. Conferma immediata SOLO per l'admin
    updated_link = await db.links.find_one({"_id": ObjectId(link_id)})
    resp = request.app.state.templates.TemplateResponse(
        "links/links_row_partial.html",
        {"request": request, "link": updated_link, "current_user": current_user}
    )
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('update', title)
    return resp

@links_router.get("/new", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def new_link_form(request: Request):
    template = "links/links_new_partial.html" if request.headers.get("hx-request") == "true" else "links/links_new.html"
    return request.app.state.templates.TemplateResponse(template, {"request": request})

@links_router.get("/list", response_class=HTMLResponse)
async def list_links_partial(request: Request, current_user=Depends(get_current_user)):
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
                        {"employment_type": {"$elemMatch": {"$in": [employment_type, "*"]}}},
                        {"employment_type": {"$exists": False}},
                        {"employment_type": []}
                    ]
                }
            ]
        }
    
    links = await db.links.find(mongo_filter).to_list(length=None)
    
    return request.app.state.templates.TemplateResponse(
        "links/links_list_partial.html",
        {
            "request": request,
            "links": links,
            "current_user": current_user
        }
    )
