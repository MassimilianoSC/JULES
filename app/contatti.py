from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse, Response
from app.deps import require_admin, get_current_user
from app.utils.save_with_notifica import save_and_notify
from app.models.contacts_model import ContactIn, ContactOut
from bson import ObjectId
from datetime import datetime
from app.constants import DEFAULT_BRANCHES, DEFAULT_HIRE_TYPES
from typing import Annotated
from app.notifiche import crea_notifica

contatti_router = APIRouter(tags=["contatti"])

@contatti_router.post(
    "/contatti/new",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(require_admin)]
)
async def create_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    bu: str = Form(None),
    team: str = Form(None),
    branch: str = Form(...),
    employment_type: str = Form(...),
    work_branch: str = Form(...),
    show_on_home: Annotated[bool, Form()] = False,
    current_user: dict = Depends(require_admin)
):
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    result = await db.contatti.insert_one({
        "name": name.strip(),
        "email": email.strip(),
        "phone": (phone or "").strip(),
        "bu": (bu or "").strip() or None,
        "team": (team or "").strip() or None,
        "branch": branch,
        "employment_type": employment_type_list,
        "work_branch": work_branch,
        "show_on_home": bool(show_on_home),
        "created_at": datetime.utcnow()
    })
    new_id = result.inserted_id
    if show_on_home:
        highlight_data = {
            "type": "contact",
            "object_id": new_id,
            "title": name.strip(),
            "created_at": datetime.utcnow(),
            "branch": branch,
            "employment_type": employment_type_list,
            "email": email.strip(),
            "phone": (phone or "").strip(),
            "bu": (bu or "").strip() or None,
            "team": (team or "").strip() or None,
            "work_branch": work_branch
        }
        print("Salvo in home_highlights (creazione):", highlight_data)
        await db.home_highlights.update_one(
            {"type": "contact", "object_id": new_id},
            {"$set": highlight_data},
            upsert=True
        )
        # --- AGGIUNTA BROADCAST HIGHLIGHT ---
        try:
            import json
            payload = {
                "type": "update_contact_highlight",
                "data": {"id": str(new_id)}
            }
            from app.ws_broadcast import broadcast_message
            await broadcast_message(json.dumps(payload))
        except Exception as e:
            print("[WebSocket] Errore broadcast su update_contact_highlight:", e)
        # --- FINE AGGIUNTA ---
    await crea_notifica(
        request=request,
        tipo="contatto",
        titolo=name.strip(),
        branch=branch,
        id_risorsa=str(new_id),
        employment_type=employment_type_list
    )
    # --- AGGIUNTA BROADCAST NOTIFICA GENERICA (come per i link) ---
    try:
        import json
        notifica = await db.notifiche.find_one({"id_risorsa": str(new_id), "tipo": "contatto"})
        payload = {
            "type": "new_notification",
            "data": {
                "id": str(notifica["_id"]),
                "message": f"È stato aggiunto un nuovo contatto: {notifica.get('titolo', '')}",
                "tipo": "contatto"
            }
        }
        from app.ws_broadcast import broadcast_message
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su new_notification contatto:", e)
    # --- FINE AGGIUNTA ---
    # --- AGGIUNTA LOGICA WEBSOCKET ---
    try:
        import json
        contact = await db.contatti.find_one({"_id": new_id})
        payload = {
            "type": "new_contact",
            "data": {
                "id": str(new_id),
                "message": f"È stato aggiunto un nuovo contatto: {contact.get('name', '')}"
            }
        }
        from app.ws_broadcast import broadcast_message
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su new_contact:", e)
    # --- FINE AGGIUNTA ---
    return RedirectResponse("/contatti", status_code=303)

@contatti_router.get("/contatti", response_class=HTMLResponse)
async def list_contacts(
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
                        {"employment_type": {"$elemMatch": {"$in": [employment_type, "*"]}}},
                        {"employment_type": {"$exists": False}},
                        {"employment_type": []}
                    ]
                }
            ]
        }
    contacts = await db.contatti.find(mongo_filter).sort("created_at", -1).to_list(None)
    if request.headers.get("HX-Request") == "true":
        return request.app.state.templates.TemplateResponse(
            "contatti/contatti_list_partial.html",
            {"request": request, "contacts": contacts, "current_user": current_user}
        )
    else:
        return request.app.state.templates.TemplateResponse(
            "contatti/contatti_index.html",
            {"request": request, "contacts": contacts, "current_user": current_user}
        )

@contatti_router.get(
    "/contatti/{contact_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)]
)
async def edit_contact_form(
    request: Request,
    contact_id: str,
    user = Depends(get_current_user)
):
    db = request.app.state.db
    contact = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    if not contact:
        raise HTTPException(404, "Contatto non trovato")
    branches = await db.branches.distinct("name")
    if not branches:
        branches = DEFAULT_BRANCHES
    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        hire_types = DEFAULT_HIRE_TYPES
    # Controllo se il contatto è in evidenza
    highlight = await db.home_highlights.find_one({"type": "contact", "object_id": ObjectId(contact_id)})
    show_on_home = bool(highlight)
    return request.app.state.templates.TemplateResponse(
        "contatti/contatti_edit_partial.html",
        {
            "request": request,
            "c": contact,
            "user": user,
            "branches": branches,
            "hire_types": hire_types,
            "show_on_home": show_on_home
        }
    )

@contatti_router.post(
    "/contatti/{contact_id}/edit",
    response_class=HTMLResponse
)
async def edit_contact_submit(
    request: Request,
    contact_id: str,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    bu: str = Form(None),
    team: str = Form(None),
    work_branch: str = Form(...),
    show_on_home: str = Form(None),
    user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    await db.contatti.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {
            "name": name.strip(),
            "email": email.strip(),
            "phone": phone.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "bu": bu.strip() if bu else None,
            "team": team.strip() if team else None,
            "work_branch": work_branch,
            "show_on_home": bool(show_on_home)
        }}
    )
    # Elimino tutte le vecchie notifiche relative a questo contatto
    delete_result = await db.notifiche.delete_many({"id_risorsa": str(contact_id), "tipo": "contatto"})
    print(f"[DEBUG] Notifiche cancellate per contatto {contact_id}: {delete_result.deleted_count}")
    # Dopo l'update, crea una nuova notifica per i nuovi destinatari
    await crea_notifica(
        request=request,
        tipo="contatto",
        titolo=name.strip(),
        branch=branch.strip(),
        id_risorsa=str(contact_id),
        employment_type=employment_type_list
    )
    print(f"[DEBUG] Nuova notifica creata per contatto {contact_id}")

    # Ripristino invio messaggio WebSocket per toast (new_notification)
    try:
        import json
        notifica = await db.notifiche.find_one({"id_risorsa": str(contact_id), "tipo": "contatto"})
        payload = {
            "type": "new_notification",
            "data": {
                "id": str(notifica["_id"]),
                "message": f"È stato modificato un contatto: {notifica.get('titolo', '')}",
                "tipo": "contatto"
            }
        }
        from app.ws_broadcast import broadcast_message
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su new_notification contatto (edit):", e)

    # --- AGGIORNAMENTO HOME_HIGHLIGHTS E BROADCAST HIGHLIGHT ---
    if show_on_home:
        highlight_data = {
            "type": "contact",
            "object_id": ObjectId(contact_id),
            "title": name.strip(),
            "created_at": datetime.utcnow(),
            "branch": branch.strip(),
            "employment_type": employment_type_list,
            "email": email.strip(),
            "phone": phone.strip() if phone else None,
            "bu": bu.strip() if bu else None,
            "team": team.strip() if team else None,
            "work_branch": work_branch
        }
        await db.home_highlights.update_one(
            {"type": "contact", "object_id": ObjectId(contact_id)},
            {"$set": highlight_data},
            upsert=True
        )
    else:
        await db.home_highlights.delete_one({"type": "contact", "object_id": ObjectId(contact_id)})
    # Broadcast WebSocket per aggiornamento highlights home
    try:
        import json
        from app.ws_broadcast import broadcast_message
        payload = {
            "type": "update_contact_highlight",
            "data": {"id": str(contact_id)}
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su update_contact_highlight:", e)

    updated = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    resp = request.app.state.templates.TemplateResponse(
        "contatti/contatti_row_partial.html",
        {"request": request, "contact": updated, "current_user": user}
    )
    resp.headers["HX-Trigger"] = "closeModal,refreshContattiList"
    
    # Inviare un solo tipo di evento WebSocket
    try:
        import json
        from app.ws_broadcast import broadcast_message
        payload = {
            "type": "update_contact",
            "data": {"id": str(contact_id)}
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su update_contact:", e)
    
    return resp

@contatti_router.get("/contatti/new", response_class=HTMLResponse)
async def new_contact(request: Request, current_user: dict = Depends(require_admin)):
    db = request.app.state.db
    branches = await db.branches.distinct("name")
    if not branches:
        branches = DEFAULT_BRANCHES

    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        hire_types = DEFAULT_HIRE_TYPES

    print("branches:", branches)        # debug: lista filiali
    print("hire_types:", hire_types)    # debug: lista tipologie assunzione
    
    return request.app.state.templates.TemplateResponse(
        "contatti/contatti_new.html",
        {
            "request": request,
            "branches": branches,
            "hire_types": hire_types
        }
    )

@contatti_router.get("/contatti/new/partial", response_class=HTMLResponse)
async def new_contact_partial(request: Request, current_user: dict = Depends(require_admin)):
    db = request.app.state.db
    branches = await db.branches.distinct("name")
    if not branches:
        branches = DEFAULT_BRANCHES

    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        hire_types = DEFAULT_HIRE_TYPES

    print("branches (partial):", branches)        # debug: lista filiali
    print("hire_types (partial):", hire_types)    # debug: lista tipologie assunzione
    
    return request.app.state.templates.TemplateResponse(
        "contatti/contatto_new_partial.html",
        {
            "request": request,
            "branches": branches,
            "hire_types": hire_types
        }
    )

@contatti_router.put("/contatti/{contact_id}", status_code=200)
async def update_contact(
    request: Request,
    contact_id: str,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    bu: str = Form(None),
    team: str = Form(None),
    branch: str = Form(...),
    employment_type: str = Form(...),
    show_on_home: Annotated[bool, Form()] = False,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    await db.contatti.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {
            "name": name.strip(),
            "email": email.strip(),
            "phone": (phone or "").strip(),
            "bu": (bu or "").strip() or None,
            "team": (team or "").strip() or None,
            "branch": branch,
            "employment_type": employment_type,
            "show_on_home": bool(show_on_home),
            "updated_at": datetime.utcnow(),
        }}
    )
    c = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    html = request.app.state.templates.TemplateResponse(
        "contatti/contatti_row_partial.html",
        {"request": request, "contact": c, "current_user": current_user},
        status_code=200
    )
    html.headers["HX-Trigger"] = "closeModal,refreshContattiList"
    return html

@contatti_router.delete("/contatti/{contact_id}", status_code=200)
async def delete_contact(
    request: Request,
    contact_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    # Ottieni il contatto prima di eliminarlo per avere le informazioni necessarie
    contact = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    if not contact:
        return PlainTextResponse("")
        
    await db.contatti.delete_one({"_id": ObjectId(contact_id)})
    await db.home_highlights.delete_one({"type": "contact", "object_id": ObjectId(contact_id)})
    
    # Crea una notifica per l'eliminazione del contatto
    await crea_notifica(
        request=request,
        tipo="contatto",
        titolo=contact["name"],
        branch=contact["branch"],
        id_risorsa=str(contact_id),
        employment_type=contact.get("employment_type")
    )
    
    # Invia il messaggio WebSocket per la notifica
    try:
        import json
        notifica = await db.notifiche.find_one({"id_risorsa": str(contact_id), "tipo": "contatto"})
        payload = {
            "type": "new_notification",
            "data": {
                "id": str(notifica["_id"]),
                "message": f"È stato eliminato un contatto: {contact['name']}",
                "tipo": "contatto"
            }
        }
        await broadcast_message(json.dumps(payload))
    except Exception as e:
        print("[WebSocket] Errore broadcast su new_notification contatto (delete):", e)
    
    # Broadcast WebSocket per rimozione e aggiornamento highlights
    try:
        import json
        from app.ws_broadcast import broadcast_message
        payload = {
            "type": "remove_contact",
            "data": {"id": contact_id}
        }
        await broadcast_message(json.dumps(payload))
        # Aggiorna highlights home
        payload_highlight = {
            "type": "update_contact_highlight",
            "data": {"id": contact_id}
        }
        await broadcast_message(json.dumps(payload_highlight))
    except Exception as e:
        print("[WebSocket] Errore broadcast su remove_contact:", e)
        
    return PlainTextResponse("")
