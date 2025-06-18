from fastapi import Request, Depends, HTTPException, Response
from bson import ObjectId
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.read_preferences import ReadPreference

# ─── FUNZIONE ORA INDIPENDENTE ─────────────────────────────
async def get_current_user(request: Request):
    """
    Restituisce l'utente autenticato oppure:
    • 401 + HX-Redirect  se la chiamata arriva da HTMX
    • 302/303            se è una navigazione "normale" del browser
    """
    uid = request.session.get("user_id")

    # ─── NIENTE SESSIONE ────────────────────────────────────────────
    if not uid:

        if "HX-Request" in request.headers:
            # 1) HTMX capisce HX-Redirect e ricarica la pagina
            raise HTTPException(
                status_code=401,
                headers={"HX-Redirect": "/login"}
            )
        # 2) Navigazione classica: 401 con HX-Redirect
        raise HTTPException(
            status_code=401,
            headers={"HX-Redirect": "/login"}
        )

    # ─── LOOK-UP DELL'UTENTE ────────────────────────────────────────
    user = await request.app.state.db.users.find_one({"_id": ObjectId(uid)})
    if not user:
        print(f"[DEBUG] Nessun utente trovato in DB per id {uid} (richiesta a {request.url.path})")
        raise HTTPException(401, "User not found")

    print(f"[DEBUG] Utente autenticato: {user.get('name')} ({user.get('email')}) per richiesta a {request.url.path}")

    # ─── OBBLIGO CAMBIO PASSWORD ───────────────────────────────────
    if user.get("must_change_pw") and request.url.path not in ("/me/password", "/logout"):
        # Se è una richiesta alle notifiche, restituisci 204 No Content
        if request.url.path.startswith("/notifiche/"):
            return Response(status_code=204)
            
        target = "/me/password?first=1"
        if "HX-Request" in request.headers:
            raise HTTPException(401, headers={"HX-Redirect": target})
        raise HTTPException(401, headers={"HX-Redirect": target})

    # tutto ok → salva l'utente nello state e restituiscilo
    request.state.user = user
    return user

async def require_admin(
    _: Request,
    user = Depends(get_current_user)
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return True

async def get_db(request: Request) -> AsyncIOMotorDatabase:
    """Database MongoDB"""
    return request.app.state.db

async def get_docs_coll(
    user = Depends(get_current_user),
    db = Depends(get_db)
) -> AsyncIOMotorCollection:
    """Collection documenti"""
    if user["role"] == "admin":
        return db.documents
    return db.documents.with_options(
        read_preference=ReadPreference.SECONDARY
    )

async def get_ai_news_collection(
    user = Depends(get_current_user),
    db = Depends(get_db)
) -> AsyncIOMotorCollection:
    """Collection ai_news branch-aware"""
    return db.ai_news