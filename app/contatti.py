from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from app.deps import require_admin, get_current_user
from app.utils.save_with_notifica import save_and_notify
from app.models.contacts_model import ContactIn, ContactOut
from bson import ObjectId
from datetime import datetime
from app.constants import DEFAULT_BRANCHES, DEFAULT_HIRE_TYPES
from typing import Annotated
from app.notifiche import crea_notifica
from app.ws_broadcast import broadcast_message, broadcast_resource_event
from app.utils.notification_helpers import create_action_notification_payload, create_admin_confirmation_trigger
import json

contatti_router = APIRouter(tags=["contatti"])

@contatti_router.post(
    "/contatti/new",
    response_class=Response,
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
            "object_id": str(new_id),
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
            {"type": "contact", "object_id": str(new_id)},
            {"$set": highlight_data},
            upsert=True
        )
        # --- AGGIUNTA BROADCAST HIGHLIGHT ---
        try:
            payload_highlight = {
                "type": "refresh_home_highlights",
                # Includiamo branch e employment_type per il filtraggio nel broadcast
                # Questi verranno usati da ws_broadcast.py se il tipo è refresh_home_highlights
                "data": {
                    "branch": branch,
                    "employment_type": employment_type_list
                }
            }
            # Passiamo branch e employment_type anche come argomenti diretti a broadcast_message
            # per assicurarci che ws_broadcast li usi per filtrare i destinatari.
            await broadcast_message(payload_highlight, branch=branch, employment_type=employment_type_list)
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

    # 📡 BROADCAST a tutti gli utenti
    u = request.state.user
    await broadcast_resource_event(
        event="add",
        item_type="contact",
        item_id=str(new_id),
        user_id=str(u["_id"]),
    )

    # 1. Notifica WebSocket per lo staff
    print(f"[DEBUG] Creazione notifica per contatto '{name}' da utente {current_user['_id']}")
    payload = create_action_notification_payload('create', 'contatto', name.strip(), str(current_user["_id"]))
    print(f"[DEBUG] Payload notifica: {payload}")
    await broadcast_message(payload, branch=branch, employment_type=employment_type, exclude_user_id=str(current_user["_id"]))
    print(f"[DEBUG] Broadcast completato")

    # 2. Conferma per l'admin
    print(f"[DEBUG] Creazione conferma admin")
    resp = Response(status_code=200)
    # Prima mostra la conferma
    resp.headers["HX-Trigger"] = create_admin_confirmation_trigger('create', name.strip())
    # Poi chiudi la modale e fai il redirect
    resp.headers["HX-Trigger-After-Settle"] = json.dumps({
        "closeModal": "true",
        "redirectToContatti": "/contatti"
    })
    print(f"[DEBUG] Headers risposta: {dict(resp.headers)}")
    return resp

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
    print("[DEBUG MODALE] Richiesta edit contatto ricevuta")
    print("[DEBUG MODALE] Contact ID:", contact_id)
    
    db = request.app.state.db
    contact = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    print("[DEBUG MODALE] Contatto trovato:", contact)
    
    if not contact:
        print("[DEBUG MODALE] Contatto non trovato!")
        raise HTTPException(404, "Contatto non trovato")
    
    branches = await db.branches.distinct("name")
    if not branches:
        print("[DEBUG MODALE] Usando branches di default")
        branches = DEFAULT_BRANCHES
    print("[DEBUG MODALE] Branches:", branches)
    
    hire_types = await db.hire_types.find().to_list(None)
    if not hire_types:
        print("[DEBUG MODALE] Usando hire_types di default")
        hire_types = DEFAULT_HIRE_TYPES
    print("[DEBUG MODALE] Hire types:", hire_types)
    
    # Controllo se il contatto è in evidenza
    highlight = await db.home_highlights.find_one({"type": "contact", "object_id": str(contact_id)})
    show_on_home = bool(highlight)
    print("[DEBUG MODALE] Show on home:", show_on_home)
    
    print("[DEBUG MODALE] Rendering template edit_partial.html")
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

@contatti_router.post("/contatti/{contact_id}/edit")
async def edit_contact_submit(request: Request, contact_id: str, user: dict = Depends(get_current_user)):
    form = await request.form()
    db = request.app.state.db
    
    name = form.get("name", "").strip()
    branch = form.get("branch", "").strip()
    employment_type_list = form.getlist("employment_type")
    
    # Aggiorna il contatto nel DB
    await db.contatti.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {
            "name": name,
            "branch": branch,
            "employment_type": employment_type_list,
            "phone": form.get("phone", "").strip(),
            "email": form.get("email", "").strip(),
            "role": form.get("role", "").strip()
        }}
    )

    # 1. Notifica mirata ai destinatari
    payload_toast = {
        "type": "new_notification",
        "data": {
            "id": str(contact_id),
            "message": f"Il contatto è stato modificato: {name.strip()}",
            "tipo": "contatto",
            "source_user_id": str(current_user["_id"])
        }
    }
    await broadcast_message(
        payload=payload_toast,
        branch=branch,
        employment_type=employment_type_list,
        exclude_user_id=str(user["_id"])
    )

    # 2. Aggiornamento highlights per tutti
    await broadcast_resource_event(event="update", item_type="contact", item_id=contact_id, user_id=str(user["_id"]))

    # 3. Conferma per l'admin via HX-Trigger
    updated = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    resp = request.app.state.templates.TemplateResponse(
        "contatti/contatti_row_partial.html",
        {"request": request, "contact": updated, "current_user": user}
    )

    admin_toast = {
        "title": "Contatto Modificato",
        "body": f"Hai aggiornato correttamente «{name}».",
        "type": "success"
    }
    resp.headers["HX-Trigger"] = json.dumps({
        "closeModal": True,
        "showToast": admin_toast
    })

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
    employment_type: str = Form(...), # Questo dovrebbe probabilmente essere una lista come in create_contact se il form lo permette
    work_branch: str = Form(None), # Aggiunto work_branch
    show_on_home: Annotated[bool, Form()] = False,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db

    # Prepara i dati da aggiornare
    update_data = {
        "name": name.strip(),
        "email": email.strip(),
        "phone": (phone or "").strip(),
        "bu": (bu or "").strip() or None,
        "team": team.strip() if team else None,
        "branch": branch, # branch di destinazione
        # employment_type dovrebbe essere gestito come lista se il form invia multipli valori o per coerenza
        "employment_type": [employment_type] if isinstance(employment_type, str) else (employment_type or []),
        "show_on_home": bool(show_on_home),
        "updated_at": datetime.utcnow(),
    }
    if work_branch: # Aggiungi work_branch solo se fornito
        update_data["work_branch"] = work_branch.strip()

    await db.contatti.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": update_data}
    )
    c = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    html = request.app.state.templates.TemplateResponse(
        "contatti/contatti_row_partial.html",
        {"request": request, "contact": c, "current_user": current_user},
        status_code=200
    )
    html.headers["HX-Trigger"] = "closeModal,refreshContattiList"
    return html

@contatti_router.delete("/contatti/{contact_id}")
async def delete_contact(
    request: Request,
    contact_id: str,
    current_user: dict = Depends(require_admin)
):
    db = request.app.state.db
    
    # 1. Recupera il contatto prima di eliminarlo
    contact = await db.contatti.find_one({"_id": ObjectId(contact_id)})
    if not contact:
        raise HTTPException(404, "Contatto non trovato")

    # 2. Elimina il contatto
    await db.contatti.delete_one({"_id": ObjectId(contact_id)})
    
    # 3. Elimina da home_highlights se presente
    await db.home_highlights.delete_one({
        "type": "contact",
        "object_id": str(contact_id)
    })

    # 4. Notifica WebSocket per lo staff (come nella creazione)
    print(f"[DEBUG] Preparazione notifica eliminazione per '{contact['name']}'")
    payload = create_action_notification_payload(
        'delete', 
        'contatto', 
        contact["name"], 
        str(current_user["_id"])
    )
    print(f"[DEBUG] Payload notifica: {payload}")
    await broadcast_message(
        payload, 
        branch=contact["branch"],
        employment_type=contact["employment_type"],
        exclude_user_id=str(current_user["_id"])
    )
    print(f"[DEBUG] Notifica inviata")

    # 5. Broadcast dell'evento per aggiornare UI
    await broadcast_resource_event(
        event="delete",
        item_type="contact",
        item_id=str(contact_id),
        user_id=str(current_user["_id"])
    )

    # 6. Se era in home, aggiorna la home
    if contact.get("show_on_home"):
        try:
            await broadcast_message({"type": "refresh_home_highlights"})
        except Exception as e:
            print("[WebSocket] Errore broadcast su delete_contact_highlight:", e)

    # 7. Conferma per l'admin
    response = Response(status_code=200)
    admin_trigger = create_admin_confirmation_trigger(
        'delete',
        contact["name"]
    )
    print("[DEBUG-CONTATTI-DELETE] Payload conferma admin:", admin_trigger)
    response.headers["HX-Trigger"] = admin_trigger
    return response
