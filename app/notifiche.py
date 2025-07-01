from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
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
    source_user_id: Optional[str] = None, # ID dell'utente che ha scatenato l'evento
    destinatario_user_id: Optional[str] = None # ID dell'utente a cui inviare il WS mirato
):
    db = request.app.state.db
    notifica_doc_data = {
        "tipo": tipo,
        "titolo": titolo,
        "branch": branch,
        "id_risorsa": id_risorsa,
        "created_at": datetime.utcnow(),
        "letta_da": [],
        # Eventualmente aggiungere source_user_id anche nel DB se utile per analisi future
        # "source_user_id": source_user_id
    }
    if employment_type is not None:
        notifica_doc_data["employment_type"] = employment_type
        print(f"[DEBUG] Creo notifica DB: tipo={tipo}, id_risorsa={id_risorsa}, employment_type={employment_type}")
    else:
        print(f"[DEBUG] Creo notifica DB: tipo={tipo}, id_risorsa={id_risorsa}, employment_type=None")

    result = await db.notifiche.insert_one(notifica_doc_data)
    notifica_id_str = str(result.inserted_id)
    print(f"[DEBUG] Notifica salvata DB: {notifica_doc_data}")

    if destinatario_user_id:
        # Invia notifica WebSocket mirata all'utente destinatario
        from app.ws_broadcast import broadcast_message # Importazione locale per evitare dipendenze circolari a livello di modulo
        payload_ws = {
            "type": "new_notification",
            "data": {
                "id": notifica_id_str,
                "message": titolo,
                "tipo": tipo,
                "source_user_id": source_user_id
            }
        }
        try:
            await broadcast_message(payload_ws, target_user_id=destinatario_user_id)
            print(f"[DEBUG] Inviato WS new_notification a {destinatario_user_id} per notifica {notifica_id_str}")
        except Exception as e:
            print(f"[ERROR] Fallito invio WS new_notification a {destinatario_user_id}: {e}")


# Funzione specializzata per le notifiche dei commenti
async def crea_notifica_commento(
    request: Request,
    news_id: str,
    comment_id: str,
    author_id: str,
    parent_id: str = None,
    mentioned_users: list = None
):
    db = request.app.state.db
    # Recupera informazioni sulla news
    news = await db.ai_news.find_one({"_id": ObjectId(news_id)})
    if not news:
        return
    # Recupera informazioni sull'autore del commento
    author = await db.users.find_one({"_id": ObjectId(author_id)})
    author_name = author.get("name", "[utente]") if author else "[utente]"
    # 1. Notifica all'autore della news se è un commento root
    if not parent_id and str(news.get("author_id")) != author_id:
        await crea_notifica(
            request=request,
            tipo="commento",
            titolo=f"{author_name} ha commentato la tua news",
            branch=news.get("branch", "*"),
            id_risorsa=f"{news_id}:{comment_id}",
            source_user_id=author_id, # Chi ha scritto il commento
            destinatario_user_id=str(news.get("author_id")) # A chi è destinata la notifica
        )
    # 2. Notifica all'autore del commento padre in caso di risposta
    if parent_id:
        parent_comment = await db.ai_news_comments.find_one({"_id": ObjectId(parent_id)})
        if parent_comment and str(parent_comment.get("author_id")) != author_id:
            # parent_author_obj = await db.users.find_one({"_id": parent_comment["author_id"]}) # Non serve recuperare l'oggetto intero
            dest_id_parent_comment_author = str(parent_comment.get("author_id"))
            await crea_notifica(
                request=request,
                tipo="risposta",
                titolo=f"{author_name} ha risposto al tuo commento",
                branch=news.get("branch", "*"),
                id_risorsa=f"{news_id}:{comment_id}",
                source_user_id=author_id, # Chi ha scritto la risposta
                destinatario_user_id=dest_id_parent_comment_author # A chi è destinata la notifica
            )
    # 3. Notifiche per le menzioni
    if mentioned_users:
        for mentioned_user_id_str in mentioned_users: # Assumendo che mentioned_users sia una lista di stringhe ID
            if mentioned_user_id_str != author_id: # Non notificare l'autore per auto-menzione
                await crea_notifica(
                    request=request,
                    tipo="menzione",
                    titolo=f"{author_name} ti ha menzionato in un commento",
                    branch=news.get("branch", "*"),
                    id_risorsa=f"{news_id}:{comment_id}",
                    source_user_id=author_id, # Chi ha scritto il commento con la menzione
                    destinatario_user_id=mentioned_user_id_str # A chi è destinata la notifica
                )


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
    if user.get("role") == "admin":
        q = {
            "branch": {"$in": ["*", branch]},
            "letta_da": {"$ne": str(user["_id"])}
        }
    else:
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
async def notifiche_count(tipo: str, request: Request, user=Depends(get_current_user)):
    if not user:
        return Response(status_code=204)
    
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    
    q = {
        "tipo": tipo,
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])},
        "$or": get_emp_type_conditions(employment_type)
    }
    count = await db.notifiche.count_documents(q)
    
    # Se il conteggio è 0, restituisci stringa vuota
    if count == 0:
        return Response(content="", media_type="text/html")
        
    return Response(content=str(count), media_type="text/html")


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
        {"request": request, "unread_links_count": "" if count == 0 else count, "u": user} # Corretto: unread_links_count
    )


# 🔹 Endpoint per ottenere il conteggio delle notifiche di tipo "contatto"
@notifiche_router.get("/notifiche/count/contatto", response_class=HTMLResponse)
async def notifiche_count_contatto(request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "tipo": "contatto",
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])},
        "$or": get_emp_type_conditions(employment_type)
    }
    count = await db.notifiche.count_documents(q)
    return request.app.state.templates.TemplateResponse(
        "components/nav_contatti_badge.html",
        {"request": request, "unread_contatti_count": "" if count == 0 else count, "u": user}
    )


# 🔹 Endpoint per ottenere il conteggio delle notifiche di tipo "documento"
@notifiche_router.get("/notifiche/count/documento", response_class=HTMLResponse)
async def notifiche_count_documento(request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "tipo": "documento",
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])} ,
        "$or": [
            {"employment_type": {"$in": [employment_type, "*"]}},
            {"employment_type": employment_type},
            {"employment_type": "*"},
            {"employment_type": {"$exists": False}}
        ]
    }
    count = await db.notifiche.count_documents(q)
    return request.app.state.templates.TemplateResponse(
        "components/nav_documenti_badge.html",
        {"request": request, "new_docs_count": "" if count == 0 else count, "u": user}
    )


# 🔹 Endpoint per ottenere il conteggio delle notifiche di tipo "news"
@notifiche_router.get("/notifiche/count/news", response_class=HTMLResponse)
async def notifiche_count_news(request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")
    q = {
        "tipo": "news",
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])},
        "$or": get_emp_type_conditions(employment_type)
    }
    count = await db.notifiche.count_documents(q)
    return request.app.state.templates.TemplateResponse(
        "components/nav_news_badge.html",
        {"request": request, "unread_news_count": "" if count == 0 else count, "u": user}
    )

# 🔹 Endpoint per ottenere il conteggio delle notifiche di tipo "commento", "risposta", "menzione" (AI News Interactions)
@notifiche_router.get("/notifiche/count/ai_interaction", response_class=HTMLResponse)
async def notifiche_count_ai_interaction(request: Request, user=Depends(get_current_user)):
    if not user:
        return Response(status_code=204)

    db = request.app.state.db
    employment_type = user.get("employment_type")
    branch = user.get("branch")

    interaction_types = ["commento", "risposta", "menzione"]

    q = {
        "tipo": {"$in": interaction_types},
        # Assumiamo che le notifiche per commenti/risposte/menzioni ereditino il branch dalla news AI
        # e che la visibilità sia quindi basata su quello e sull'employment type dell'utente.
        "branch": {"$in": ["*", branch]},
        "letta_da": {"$ne": str(user["_id"])},
        "$or": get_emp_type_conditions(employment_type)
    }
    count = await db.notifiche.count_documents(q)

    return request.app.state.templates.TemplateResponse(
        "components/nav_ai_news_badge.html",
        {"request": request, "unread_ai_interaction_count": "" if count == 0 else count, "u": user}
    )
