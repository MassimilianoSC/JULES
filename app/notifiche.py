from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from bson import ObjectId
from datetime import datetime

# 🔸 Niente più import da main.py!
from app.deps import get_current_user                       # ✅
# Usa sempre request.app.state.templates per i render        # ✅

notifiche_router = APIRouter(tags=["notifiche"])


# 🔹 Funzione da usare ovunque per creare una notifica
async def crea_notifica(
    request: Request,
    tipo: str,
    titolo: str,
    branch: str,
    id_risorsa: str,
    employment_type=None,
):
    db = request.app.state.db
    notifica = {
        "tipo": tipo,
        "titolo": titolo,
        "branch": branch,
        "id_risorsa": id_risorsa,
        "created_at": datetime.utcnow(),
        "letta_da": [],
    }
    if employment_type is not None:
        notifica["employment_type"] = employment_type
        print(f"[DEBUG] Creo notifica: tipo={tipo}, id_risorsa={id_risorsa}, employment_type={employment_type}")
    else:
        print(f"[DEBUG] Creo notifica: tipo={tipo}, id_risorsa={id_risorsa}, employment_type=None")
    await db.notifiche.insert_one(notifica)
    print(f"[DEBUG] Notifica salvata: {notifica}")


# Funzione di utilità per condizioni employment_type
def get_emp_type_conditions(user_emp_type):
    conds = [
        {"employment_type": {"$exists": False}},
        {"employment_type": []},
        {"employment_type": {"$in": ["*"]}}
    ]
    if user_emp_type:
        conds.append({"employment_type": {"$in": [user_emp_type]}})
    return conds


# 🔹 Pagina con elenco completo delle notifiche non lette
@notifiche_router.get("/notifiche", response_class=HTMLResponse)
async def notifiche_page(request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])},
        "$or": get_emp_type_conditions(employment_type)
    }
    notifiche = (
        await db.notifiche.find(q)
        .sort("created_at", -1)
        .to_list(None)
    )
    return request.app.state.templates.TemplateResponse(
        "notifiche/index.html",
        {"request": request, "user": user, "notifiche": notifiche},
    )


# 🔹 Notifiche inline, mostrate in alto in ogni pagina
@notifiche_router.get("/notifiche/inline", response_class=HTMLResponse)
async def notifiche_inline(request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])},
        "$or": get_emp_type_conditions(employment_type)
    }
    print(f"[DEBUG SERVER] Filtro notifiche inline applicato: {q}")
    notifiche_trovate_nel_db = await db.notifiche.find(q).sort("created_at", -1).to_list(3)
    print(f"[DEBUG SERVER] Notifiche effettivamente trovate dal DB per inline: {notifiche_trovate_nel_db}")
    return request.app.state.templates.TemplateResponse(
        "notifiche/inline_partial.html",
        {"request": request, "notifiche": notifiche_trovate_nel_db},
    )


# 🔹 API per segnare una notifica come "letta"
@notifiche_router.post("/notifiche/{id}/letta")
async def segna_letta(id: str, request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    await db.notifiche.update_one(
        {"_id": ObjectId(id)}, {"$addToSet": {"letta_da": str(user["_id"])}}
    )
    return JSONResponse({"ok": True}, headers={"HX-Trigger": "refresh-notifiche"})


# 🔹 Endpoint per il pallino rosso nel menu
@notifiche_router.get("/notifiche/count/{tipo}", response_class=HTMLResponse)
async def notifiche_count(
        tipo: str,
        request: Request,
        user = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "tipo": tipo,
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])} ,
        "$or": get_emp_type_conditions(employment_type)
    }
    count = await db.notifiche.count_documents(q)
    if tipo == "link":
        return request.app.state.templates.TemplateResponse(
            "components/nav_links_badge.html",
            {"request": request, "unread_link_count": count, "u": user}
        )
    html = (f'<span class="absolute -top-1 right-2 bg-red-500 text-white text-xs rounded-full px-2 py-0.5 font-bold shadow">{count}</span>'
            if count > 0 else '')
    return HTMLResponse(html)


# Endpoint per segnare tutte le notifiche di un certo tipo come lette
@notifiche_router.post("/notifiche/mark-read/{tipo}")
async def mark_all_read(tipo: str, request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    filtro = {
        "tipo": tipo,
        "letta_da": {"$ne": str(user["_id"])},
        "branch": {"$in": ["*", branch]},
        "$or": get_emp_type_conditions(employment_type)
    }
    result = await db.notifiche.update_many(
        filtro,
        {"$addToSet": {"letta_da": str(user["_id"])}}
    )
    return {"ok": True}


# 🔹 Endpoint per ottenere l'ultima notifica non letta di un certo tipo
@notifiche_router.get("/notifiche/ultima")
async def ultima_notifica(request: Request, user=Depends(get_current_user), tipo: str = Query(None)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "letta_da": {"$ne": str(user["_id"])}
    }
    if tipo:
        q["tipo"] = tipo
    q["branch"] = {"$in": ["*", branch]}
    q["$or"] = get_emp_type_conditions(employment_type)
    notifica = await db.notifiche.find(q).sort("created_at", -1).limit(1).to_list(1)
    if not notifica:
        return {"_id": None, "titolo": None}
    n = notifica[0]
    return {"_id": str(n["_id"]), "titolo": n.get("titolo", "Nuova notifica")}


# 🔹 Endpoint per ottenere il conteggio delle notifiche di tipo "link"
@notifiche_router.get("/notifiche/count/link", response_class=HTMLResponse)
async def notifiche_count_link(request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "tipo": "link",
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])},
        "$or": get_emp_type_conditions(employment_type)
    }
    count = await db.notifiche.count_documents(q)
    return request.app.state.templates.TemplateResponse(
        "components/nav_links_badge.html",
        {"request": request, "unread_link_count": count, "u": user}
    )
