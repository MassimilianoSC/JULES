from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from app.deps import require_admin, get_current_user
from app.utils.save_with_notifica import save_and_notify
from app.models.links_model import LinkIn, LinkOut
from bson import ObjectId
from datetime import datetime
from app.notifiche import crea_notifica
from app.ws_broadcast import broadcast_message

links_router = APIRouter(tags=["links"])

@links_router.post(
    "/links/new",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(require_admin)]
)
async def create_link(
    request: Request,
    title: str = Form(...),
    url: str = Form(...),
    description: str = Form(None),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    show_on_home: str = Form(None)
):
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    result = await save_and_notify(
        request=request,
        collection="links",
        payload={
            "title": title.strip(),
            "url": url.strip(),
            "description": description.strip() if description else None,
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "show_on_home": bool(show_on_home)
        },
        tipo="link",
        titolo=title.strip(),
        branch=branch.strip()
    )
    # Recupera l'id del link appena creato
    db = request.app.state.db
    link = await db.links.find_one({"title": title.strip(), "url": url.strip()})
    if show_on_home:
        await db.home_highlights.update_one(
            {"type": "link", "object_id": link["_id"]},
            {"$set": {
                "type": "link",
                "object_id": link["_id"],
                "title": title.strip(),
                "created_at": datetime.utcnow(),
                "branch": branch.strip(),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "link", "object_id": link["_id"]})
    # Notifica via WebSocket
    try:
        import json
        notifica = await db.notifiche.find_one({"id_risorsa": str(link["_id"]), "tipo": "link"})
        payload = {
            "type": "new_notification",
            "data": {
                "id": str(notifica["_id"]),
                "message": f"È stato pubblicato un nuovo link: {notifica.get('titolo', '')}"
            }
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast:", e)
    # Dopo la creazione del link
    print(f"[DEBUG] Link creato: title={title.strip()}, branch={branch.strip()}, employment_type={employment_type_list}")
    # Dopo la creazione della notifica (dopo save_and_notify)
    notifica = await db.notifiche.find_one({"id_risorsa": str(link["_id"]), "tipo": "link"})
    print(f"[DEBUG] Notifica creata: {notifica}")
    return RedirectResponse("/links", status_code=303)

@links_router.get("/links", response_class=HTMLResponse)
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
                        {"employment_type": {"$in": [employment_type, "*"]}},
                        {"employment_type": employment_type},
                        {"employment_type": "*"},
                        {"employment_type": {"$exists": False}}
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
    "/links/{link_id}/edit",
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

@links_router.delete("/links/{link_id}", status_code=200, dependencies=[Depends(require_admin)])
async def delete_link(request: Request, link_id: str, user=Depends(get_current_user)):
    db = request.app.state.db
    await db.links.delete_one({"_id": ObjectId(link_id)})
    await db.home_highlights.delete_one({"type": "link", "object_id": ObjectId(link_id)})
    # Broadcast WebSocket per aggiornamento real-time
    try:
        import json
        payload = {
            "type": "remove_link",
            "data": {"id": link_id}
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su delete_link:", e)
    return PlainTextResponse("")

@links_router.post("/links/{link_id}/edit", dependencies=[Depends(require_admin)])
async def edit_link(request: Request, link_id: str, user=Depends(get_current_user)):
    form_data = await request.form()
    db = request.app.state.db
    employment_type = form_data.get("employment_type")
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    await db.links.update_one(
        {"_id": ObjectId(link_id)},
        {"$set": {
            "title": form_data.get("title"),
            "url": form_data.get("url"),
            "description": form_data.get("description"),
            "branch": form_data.get("branch"),
            "employment_type": employment_type_list,
            "show_on_home": "show_on_home" in form_data
        }}
    )
    # Gestione home_highlights
    if "show_on_home" in form_data:
        await db.home_highlights.update_one(
            {"type": "link", "object_id": ObjectId(link_id)},
            {"$set": {
                "type": "link",
                "object_id": ObjectId(link_id),
                "title": form_data.get("title"),
                "created_at": datetime.utcnow(),
                "branch": form_data.get("branch"),
                "employment_type": employment_type_list
            }},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "link", "object_id": ObjectId(link_id)})
    # Elimino tutte le vecchie notifiche relative a questo link
    delete_result = await db.notifiche.delete_many({"id_risorsa": str(link_id), "tipo": "link"})
    print(f"[DEBUG] Notifiche cancellate per link {link_id}: {delete_result.deleted_count}")
    # Dopo l'update, crea una nuova notifica per i nuovi destinatari
    await crea_notifica(
        request=request,
        tipo="link",
        titolo=form_data.get("title"),
        branch=form_data.get("branch"),
        id_risorsa=str(link_id),
        employment_type=employment_type_list
    )
    updated = await db.links.find_one({"_id": ObjectId(link_id)})
    resp = request.app.state.templates.TemplateResponse(
        "links/link_row_partial.html",
        {"request": request, "l": updated, "user": user}
    )
    resp.headers["HX-Trigger"] = "closeModal"
    # Broadcast WebSocket per aggiornamento real-time dopo modifica
    try:
        import json
        payload = {
            "type": "update_link",
            "data": {"id": link_id}
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su update_link:", e)
    return resp

@links_router.get("/links/new", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def new_link_form(request: Request):
    template = "links/links_new_partial.html" if request.headers.get("hx-request") == "true" else "links/links_new.html"
    return request.app.state.templates.TemplateResponse(template, {"request": request})
