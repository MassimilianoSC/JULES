# ---------------------------- IMPORT ---------------------------------
from dotenv import load_dotenv
from pathlib import Path

# Percorso assoluto del file .env (nella root del progetto)
ENV_PATH = Path(__file__).resolve().parent / '.env'  # vecchio percorso
print(f"\n=== LOADING ENV FILE ===\nPath: {ENV_PATH}\nExists: {ENV_PATH.exists()}\n")
load_dotenv()  # Carica .env dalla directory corrente

import os
if "SESSION_SECRET" not in os.environ:
    raise RuntimeError("SESSION_SECRET must be defined")
SECRET_KEY = os.environ["SESSION_SECRET"]        # ← senza default

print("\n=== APP SECRET KEY ===")
print(f"First 10 chars: {SECRET_KEY[:10]}")
print(f"Length: {len(SECRET_KEY)}")

import os, secrets
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Literal, Dict
from datetime import date, datetime, timedelta
from bson import ObjectId    
from app.news import news_router
from app.links import links_router
from app.documents import documents_router, BASE_DOCS_DIR
from app.contatti import contatti_router
from app.deps import require_admin, get_current_user
from app.notifiche import notifiche_router
from app.ai_news import ai_news_router
from app.soci import soci_router
from app.organigramma import organigramma_router
from app.ws_broadcast import websocket_main, broadcast_resource_event, get_ws_user

import motor.motor_asyncio
from bson import ObjectId
from passlib.hash import bcrypt
from pydantic import BaseModel, Field

from fastapi import (
    FastAPI, Request, Depends, HTTPException,
    Form, Response, APIRouter, status,
    UploadFile, File, Query, WebSocket, WebSocketDisconnect
)
from fastapi.responses import (
    HTMLResponse, RedirectResponse,
    FileResponse, Response, JSONResponse
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorClient
from pathlib import Path
from werkzeug.utils import secure_filename
from pymongo.errors import DuplicateKeyError
from markdown_it import MarkdownIt
import bleach
from logging.handlers import RotatingFileHandler
from pymongo import DESCENDING, ASCENDING

# --- LOGGING ---------------------------------------------------------
import logging

# Configura il logger principale
logging.basicConfig(level=logging.INFO)

# Crea un logger specifico per l'applicazione
logger = logging.getLogger("intranet")
logger.setLevel(logging.INFO)

# Rimuovi gli handler esistenti per evitare duplicati
logger.handlers = []

# Formattatore per i log su file
file_formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

# Formattatore per i log su console (più conciso)
console_formatter = logging.Formatter(
    '[%(levelname)s] %(message)s'
)

# Handler per il file di log
file_handler = RotatingFileHandler(
    'intranet.log',
    maxBytes=1024*1024,  # 1MB
    backupCount=5
)
file_handler.setFormatter(file_formatter)
file_handler.setLevel(logging.DEBUG)

# Handler per la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(console_formatter)
console_handler.setLevel(logging.INFO)

# Aggiungi gli handler al logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Riduci il livello di log per alcuni moduli troppo verbosi
logging.getLogger("motor").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

# --------------------------- CONFIG ----------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/intranet")

limiter = Limiter(key_func=get_remote_address)
templates = Jinja2Templates(directory="templates")
templates.env.globals["datetime"] = datetime

def format_datetime(dt):
    """Formatta una data in formato leggibile"""
    if not dt:
        return ""
    return dt.strftime("%d/%m/%Y %H:%M")

def markdown_filter(text):
    md = MarkdownIt("commonmark", {"breaks": True, "html": False})
    html = md.render(text or "")
    safe_html = bleach.clean(
        html,
        tags=[
            'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'strong', 'ul', 'p', 'pre', 'br', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'
        ],
        attributes={'a': ['href', 'title', 'target'], 'span': ['class']},
        strip=True
    )
    return safe_html

# Registra i filtri
templates.env.filters["markdown"] = markdown_filter
templates.env.filters["format_datetime"] = format_datetime

print("Filtri disponibili:", templates.env.filters.keys())

# Costanti per i percorsi
BASE_DOCS_DIR = Path("media/docs")   # cartella radice documenti
FOTO_DIR = Path("media/foto")        # cartella radice foto profilo

# Definizione lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    app.state.db = client.get_default_database()
    await app.state.db.users.create_index("email", unique=True)
    yield
    client.close()

# --------------------------- APP INIT ----------------------------------
app = FastAPI(lifespan=lifespan)                 

app.state.templates = templates
print("\n=== APP STATE SECRET KEY ===")
print(f"Setting app.state.secret_key (first 10 chars): {SECRET_KEY[:10]}...")
app.state.secret_key = SECRET_KEY                

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

print("\n=== MIDDLEWARE SECRET KEY ===")
print(f"Configuring SessionMiddleware with key (first 10 chars): {SECRET_KEY[:10]}...")

# Stampa il valore esatto della chiave per debug (RIMUOVERE IN PRODUZIONE!)
print("DEBUG - Actual secret key:", SECRET_KEY)

app.add_middleware(                              
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
)

# Debug middleware configuration
print("\n=== SESSION MIDDLEWARE CONFIG ===")
print("Secret Key Length:", len(SECRET_KEY))
print("Middleware:", [m.cls.__name__ for m in app.user_middleware])

app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

# -------------------- DEPENDENCIES & UTILITIES -----------------------
CSRF_SESSION_KEY = "_csrf_token"

async def get_db(request: Request):
    return request.app.state.db

def get_csrf_token(request: Request) -> str:
    tok = request.session.get(CSRF_SESSION_KEY)
    if not tok:
        tok = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = tok
    return tok

async def validate_csrf(request: Request):
    form  = await request.form()
    sent  = form.get("_csrf") or request.headers.get("X-CSRF-Token")
    good  = request.session.get(CSRF_SESSION_KEY)
    if sent != good:
        raise HTTPException(403, "Invalid CSRF token")

def to_str_id(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"]); return doc

# ----------------------- PYDANTIC MODELS -----------------------------
class UserIn(BaseModel):
    name: str
    email: str
    role: Literal["admin", "staff"]
    password: str
    # -------------- NUOVI CAMPI CSV -----------------
    branch: Literal["HQE", "HQ ITALIA", "HQIA"]
    employment_type: Literal["TD", "TI", "AP", "CO", "*"]  # Nuovo campo
    bu: Optional[str] = None            # CDC - BU
    team: Optional[str] = None          # CDC - TEAM
    birth_date: Optional[date] = None   # DATA DI NASCITA
    sex: Optional[Literal["M", "F"]] = None
    citizenship: Optional[str] = None
    pinned_items: Optional[List[Dict[str, str]]] = Field(default_factory=list)  # [{type: "ai_news", id: "123"}, ...]

class UserOut(UserIn):
    id: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[Literal["admin", "staff"]] = None
    password: Optional[str] = None
    # i campi HR diventano editabili solo via API admin
    branch: Optional[Literal["HQE", "HQ ITALIA", "HQIA"]] = None
    employment_type: Optional[Literal["TD", "TI", "AP", "CO", "*"]] = None  # Nuovo campo
    bu: Optional[str] = None
    team: Optional[str] = None
    birth_date: Optional[date] = None
    sex: Optional[Literal["M", "F"]] = None
    citizenship: Optional[str] = None

class PinIn(BaseModel):
    type: str
    id: str

# --------------------------- ROUTE UI --------------------------------
from fastapi.responses import RedirectResponse

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user = Depends(get_current_user)):
    db = request.app.state.db
    now = datetime.utcnow()

    # --- NUOVA LOGICA PER RECUPERARE LE NEWS ---
    
    # 1. Filtro per le news non scadute
    news_filter = {
        "$or": [
            {"expires_at": None},
            {"expires_at": {"$gt": now}}
        ]
    }

    # 2. Logica di ordinamento: Prima le pinnate, poi per priorità, poi per data
    sort_logic = [("pinned", DESCENDING), ("priority", ASCENDING), ("created_at", DESCENDING)]

    # 3. Esegui la query
    news_items = await db.news.find(news_filter).sort(sort_logic).to_list(length=None)

    # --- LOGICA PER GLI ALTRI HIGHLIGHTS (documenti, link, etc.) ---
    highlights_filter = {
        "type": {"$ne": "news"} 
    }
    other_highlights = await db.home_highlights.find(highlights_filter).to_list(length=None)
    
    # Uniamo le news con gli altri highlights
    all_highlights = news_items + other_highlights

    # Converti gli ObjectId in stringhe e uniforma l'uso di object_id
    for h in all_highlights:
        if "_id" in h:
            h["_id"] = str(h["_id"])
        if "id" in h:
            if "object_id" not in h:
                h["object_id"] = str(h["id"])
            del h["id"]
        if "object_id" in h:
            h["object_id"] = str(h["object_id"])

    # Converti gli ID dei pin in stringhe
    if "pinned_items" in user:
        for pin in user["pinned_items"]:
            if "id" in pin:
                pin["id"] = str(pin["id"])

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "highlights": all_highlights,
            "news_items": news_items
        }
    )

@app.get("/home/highlights/partial", response_class=HTMLResponse)
async def home_highlights_partial(request: Request, user = Depends(get_current_user)):
    db = request.app.state.db
    
    # Definisci il filtro base per gli highlights in base al ruolo e ai permessi dell'utente
    user_branch = user.get("branch")
    user_employment_type = user.get("employment_type")

    highlights_filter = {}
    if user.get("role") != "admin":
        conditions = []
        # Filtro per branch
        if user_branch:
            conditions.append({"$or": [{"branch": "*"}, {"branch": user_branch}]})
        else: # Utente senza branch specifico, può vedere solo quelli per tutti '*'
            conditions.append({"branch": "*"})

        # Filtro per employment_type
        if user_employment_type:
            conditions.append({"$or": [
                {"employment_type": "*"},
                {"employment_type": user_employment_type}, # Caso semplice: stringa singola
                {"employment_type": {"$elemMatch": {"$in": [user_employment_type, "*"]}}}, # Caso lista
                {"employment_type": {"$exists": False}},
                {"employment_type": []}
            ]})
        else: # Utente senza employment_type specifico
             conditions.append({"$or": [
                {"employment_type": "*"},
                {"employment_type": {"$exists": False}},
                {"employment_type": []}
            ]})

        if conditions:
            highlights_filter["$and"] = conditions

    highlights = await db.home_highlights.find(highlights_filter).sort([("created_at", DESCENDING)]).to_list(length=None)
    
    # Converti gli ObjectId in stringhe e uniforma l'uso di object_id
    for h in highlights:
        if "_id" in h:
            h["_id"] = str(h["_id"])
        if "id" in h:
            # Converti id in object_id se non esiste già
            if "object_id" not in h:
                h["object_id"] = str(h["id"])
            del h["id"]  # Rimuovi il vecchio id
        if "object_id" in h:
            h["object_id"] = str(h["object_id"])
    
    # Converti gli ID dei pin in stringhe
    if "pinned_items" in user:
        for pin in user["pinned_items"]:
            if "id" in pin:
                pin["id"] = str(pin["id"])
    
    # Il filtraggio è già stato fatto dalla query MongoDB, quindi `highlights` ora contiene solo quelli pertinenti.
    # Rimuoviamo il filtraggio Python ridondante.
    
    return templates.TemplateResponse(
        "partials/home_highlights.html", # Assicurati che il nome del template sia corretto
        {
            "request": request,
            "user": user,
            "highlights": highlights # Passa direttamente gli highlights filtrati dal DB
        }
    )

@app.get("/home/news_ticker/partial", response_class=HTMLResponse)
async def home_news_ticker_partial(request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    news = await db.news.find().to_list(length=None)
    news = sorted(news, key=lambda x: x["created_at"], reverse=True)
    return request.app.state.templates.TemplateResponse(
        "partials/news_ticker.html",
        {"request": request, "news": news, "user": user}
    )

# ---- AUTH ----
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", 302)
    return templates.TemplateResponse(
        "login.html", {"request": request}
    )

@app.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, db=Depends(get_db),
                email: str = Form(...), password: str = Form(...)):
    user = await db.users.find_one({"email": email.lower()})
    if not user or not bcrypt.verify(password, user["pass_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Credenziali errate"}
        )
    request.session["user_id"] = str(user["_id"])
    if user.get("must_change_pw"):
        return RedirectResponse("/me/password?first=1", 303)
    return RedirectResponse("/", 302)

@app.get("/logout")
async def logout(request: Request):
    """
    Gestisce il logout pulendo correttamente la sessione e il cookie
    """
    # Log per debug
    logger.debug("Logout - Pulisco la sessione e cancello il cookie")
    logger.debug("Cookie prima della pulizia: %s", request.cookies.get("session"))
    
    # Pulisce la sessione
    request.session.clear()
    
    # Crea la risposta di redirect
    response = RedirectResponse("/login", status_code=302)
    
    # Cancella esplicitamente il cookie di sessione
    response.delete_cookie(
        "session",
        path="/",              # Importante: stesso path usato da SessionMiddleware
        secure=False,          # Deve corrispondere al secure= del SessionMiddleware
        httponly=True,         # Cookie accessibile solo via HTTP
        samesite="lax"         # Stesso valore del SessionMiddleware
    )
    
    logger.debug("Logout completato - Cookie cancellato")
    return response

# ---- CAMBIO PASSWORD ----
@app.get("/me/password", response_class=HTMLResponse)
async def change_pw_form(request: Request):
    return templates.TemplateResponse(
        "auth/change_pw.html",
        {"request": request, "csrf_token": get_csrf_token(request)}
    )

@app.post("/me/password", response_class=HTMLResponse,
          dependencies=[Depends(validate_csrf)])
async def change_pw_submit(request: Request, db=Depends(get_db),
    old_pw: str = Form(...), new_pw: str = Form(...),
    user = Depends(get_current_user)
):
    if not bcrypt.verify(old_pw, user["pass_hash"]):
        return templates.TemplateResponse(
            "auth/change_pw.html",
            {"request": request, "error": "Password errata",
             "csrf_token": get_csrf_token(request)}
        )
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"pass_hash": bcrypt.hash(new_pw),
                  "must_change_pw": False}}
    )
    return RedirectResponse("/", 303)

# ---- UTENTI (admin) ----
@app.get("/users", response_class=HTMLResponse,
         dependencies=[Depends(require_admin)])
async def users_page(
    request: Request,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
    q: str | None = Query(None, description="search text"),
    field: str = Query("name", description="search field"),
):
    mongo_filter: dict = {}
    allowed_fields = ["name", "role", "branch", "employment_type", "bu", "team"]
    if q:
        regex = {"$regex": ' '.join(q.split()), "$options": "i"}
        if field in allowed_fields:
            mongo_filter[field] = regex
        else:
            mongo_filter["$or"] = [
                {"name": regex},
                {"role": regex},
                {"branch": regex},
                {"employment_type": regex},
                {"bu": regex},
                {"team": regex},
            ]
    users = [to_str_id(u) for u in await db.users.find(mongo_filter).to_list(length=None)]
    return templates.TemplateResponse(
        "users/index.html",
        {
            "request": request,
            "users": users,
            "query": q or "",
            "field": field,
            "csrf_token": get_csrf_token(request),
            "current_user": current_user,
        }
    )

@app.get("/users/new", response_class=HTMLResponse,
         dependencies=[Depends(require_admin)])
async def new_user_form(request: Request):
    return templates.TemplateResponse(
        "users/new.html", {"request": request}
    )

@app.post("/users/new", dependencies=[Depends(require_admin)])
async def create_user_ui(
    request: Request, db=Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form(...),  # Nuovo campo
    bu: str | None = Form(None),
    team: str | None = Form(None),
    birth_date: str | None = Form(None),   # dd/mm/yyyy o yyyy-mm-dd
    sex: str | None = Form(None),          # M / F
    citizenship: str | None = Form(None),
    password: str = Form(...),
):
    try:
        await db.users.insert_one({
            "name": name.strip(),
            "email": email.lower(),
            "role": role,
            "branch": branch.strip(),
            "employment_type": employment_type.strip(),  # Nuovo campo
            "bu": bu or None,
            "team": team or None,
            "birth_date": birth_date or None,
            "sex": sex or None,
            "citizenship": citizenship or None,
            "pass_hash": bcrypt.hash(password),
            "must_change_pw": True
        })
        return RedirectResponse("/users", 303)
    except DuplicateKeyError:
        # Mostra errore e ripopola il form
        return templates.TemplateResponse(
            "users/new.html",
            {
                "request": request,
                "error": "Esiste già un utente con questa email!",
                "name": name,
                "email": email,
                "role": role,
                "branch": branch,
                "employment_type": employment_type,
                "bu": bu,
                "team": team,
                "birth_date": birth_date,
                "sex": sex,
                "citizenship": citizenship,
            }
        )

@app.get("/users/{user_id}/edit", response_class=HTMLResponse,
         dependencies=[Depends(require_admin)])
async def edit_user_form(request: Request, user_id: str,
                         db=Depends(get_db)):
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "users/edit_partial.html",
        {"request": request, "user": to_str_id(user)}
    )

@app.post("/users/{user_id}/edit", response_class=HTMLResponse,
          dependencies=[Depends(require_admin)])
async def edit_user_submit(
    request: Request, user_id: str, db=Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form(...),  # Nuovo campo
    bu: str | None = Form(None),
    team: str | None = Form(None),
    birth_date: str | None = Form(None),
    sex: str | None = Form(None),
    citizenship: str | None = Form(None),
):
    logger.info("USER-EDIT start id=%s", user_id)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "name": name,
            "email": email.lower(),
            "role": role,
            "branch": branch.strip(),
            "employment_type": employment_type.strip(),  # Nuovo campo
            "bu": bu or None,
            "team": team or None,
            "birth_date": birth_date or None,
            "sex": sex or None,
            "citizenship": citizenship or None,
        }}
    )
    updated = await db.users.find_one({"_id": ObjectId(user_id)})

    resp = templates.TemplateResponse(
        "users/card_partial.html",
        {
            "request": request, "u": to_str_id(updated),
            "user": request.state.user        # necessario per futuri riferimenti
        }
    )
    resp.headers["HX-Trigger"] = "closeModal"
    logger.info("USER-EDIT done id=%s  (closeModal)", user_id)
    return resp

from fastapi import Response


@app.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: str, db=Depends(get_db)):
    await db.users.delete_one({"_id": ObjectId(user_id)})
    return Response(status_code=200)





# --------------------------- ROUTE API -------------------------------
# Admin-only API router
admin_api = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(require_admin)]
)

@admin_api.get("/", response_model=list[UserOut])
async def api_list(db=Depends(get_db)):
    docs = await db.users.find().to_list(length=None)
    return [{"id": str(d["_id"]), **d, "password": None} for d in docs]

@admin_api.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def api_create(user: UserIn, db=Depends(get_db)):
    doc = user.dict(exclude={"password"})
    doc["email"] = doc["email"].lower()
    doc["pass_hash"] = bcrypt.hash(user.password)
    doc["must_change_pw"] = True
    res = await db.users.insert_one(doc)
    saved = await db.users.find_one({"_id": res.inserted_id})
    return {"id": str(saved["_id"]), **user.dict(exclude={"password"})}

@admin_api.patch("/{user_id}", response_model=UserOut)
async def api_update(user_id: str, patch: UserUpdate, db=Depends(get_db)):
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": patch.dict(exclude_unset=True)}
    )
    updated = await db.users.find_one({"_id": ObjectId(user_id)})
    return {"id": user_id, **to_str_id(updated)}

@admin_api.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete(user_id: str, db=Depends(get_db)):
    await db.users.delete_one({"_id": ObjectId(user_id)})
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Register the router with the main app
app.include_router(admin_api)
app.include_router(news_router)
app.include_router(links_router)
app.include_router(documents_router)
app.include_router(contatti_router)
app.include_router(notifiche_router)
app.include_router(ai_news_router)
app.include_router(soci_router)
app.include_router(organigramma_router)



@app.get("/me", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "profile.html",
        {"request": request,
         "user": user,
         "csrf_token": get_csrf_token(request)}   # Aggiungo il token CSRF
    )


# ---- DEPENDENCY: collection documenti branch-aware ------------------

async def get_docs_coll(
    user = Depends(get_current_user),
    db   = Depends(get_db)
) -> AsyncIOMotorCollection:
    """Restituisce la collection 'documents' filtrata per filiale
    se l'utente non è admin."""
    coll = db.documents
    if user["role"] != "admin":
        # MongoEngine style: preferiamo fare il filtro nella query
        # direttamente nella rotta, ma lasciamo qui l'helper.
        coll = coll.with_options()
    return coll

# ---- DOCUMENTI ------------------------------------------------------

@app.get("/documents", response_class=HTMLResponse)
async def list_documents(
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
    documents = await db.documents.find(mongo_filter).sort("uploaded_at", -1).to_list(None)

    # PATCH: segna tutte le notifiche documento come lette per l'utente
    user_id = str(current_user["_id"])
    result = await db.notifiche.update_many(
        {"tipo": "documento", "letta_da": {"$ne": user_id}},
        {"$push": {"letta_da": user_id}}
    )
    resp = request.app.state.templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "documents": documents,
            "current_user": current_user
        }
    )
    import json
    if result.modified_count > 0:
        resp.headers["HX-Trigger"] = json.dumps({"refreshDocumentiBadgeEvent": "true"})
    return resp

# ---- UPLOAD (solo admin) -------------------------------------------

@app.get("/documents/upload", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def upload_form(request: Request, db: AsyncIOMotorClient = Depends(get_db)): # Aggiunto db dependency
    context = {"request": request}
    if request.headers.get("hx-request") == "true":
        template_name = "documents/upload_partial.html"
        # Recupera branches e hire_types per il partial, come facciamo per altri form partial
        # Questo presuppone che tu abbia una collezione 'branches' e 'hire_types' o costanti
        branches = await db.branches.distinct("name") # Esempio, adatta se necessario
        if not branches: branches = ["HQE", "HQ ITALIA", "HQIA", "*"] # Fallback

        hire_types = await db.hire_types.find().to_list(None) # Esempio, adatta se necessario
        if not hire_types: hire_types = [{"id": "*", "label": "Tutte"}] # Fallback

        context["branches"] = branches
        context["hire_types"] = hire_types
    else:
        template_name = "documents/upload.html"
        # Anche il form completo potrebbe aver bisogno di branches e hire_types se li usa direttamente
        # o tramite l'include "components/branch_and_hire_selects.html"
        branches = await db.branches.distinct("name")
        if not branches: branches = ["HQE", "HQ ITALIA", "HQIA", "*"]

        hire_types = await db.hire_types.find().to_list(None)
        if not hire_types: hire_types = [{"id": "*", "label": "Tutte"}]

        context["branches"] = branches
        context["hire_types"] = hire_types

    return templates.TemplateResponse(template_name, context)

@app.post("/documents/upload", dependencies=[Depends(require_admin)])
async def upload_submit(
    request: Request,
    title: str = Form(...),
    branch: str = Form(...),
    tags: str | None = Form(None),      # csv "ISO,Qualità"
    file: UploadFile = File(...),
    docs_coll: AsyncIOMotorCollection = Depends(get_docs_coll),
):
    # 1. salva su disco in media/docs/<branch>/
    target_dir = DOCS_DIR if branch == "*" else DOCS_DIR / branch
    target_dir.mkdir(parents=True, exist_ok=True)

    # nome di file sicuro
    safe_name = secure_filename(file.filename)
    
    # path finale del file
    filepath = target_dir / safe_name
    
    # salva il file
    with filepath.open("wb") as out:
        content = await file.read()
        out.write(content)

    # 2. salva metadati in Mongo
    doc = {
        "title": title.strip(),
        "filename": str(filepath.relative_to(DOCS_DIR)),
        "branch": branch,
        "tags": [t.strip() for t in tags.split(",")] if tags else [],
        "uploaded_at": datetime.utcnow(),
        "uploader_id": request.state.user["_id"],
    }
    await docs_coll.insert_one(doc)

    return RedirectResponse("/documents", status_code=303)

# ---- ELIMINA DOCUMENTO (solo admin) --------------------------------

@app.delete("/documents/{doc_id}", status_code=200,
            dependencies=[Depends(require_admin)])
async def delete_document(
    doc_id: str,
    docs_coll: AsyncIOMotorCollection = Depends(get_docs_coll)
):
    """Rimuove entry DB + file fisico (solo admin)."""
    doc = await docs_coll.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Documento non trovato")

    # cancella file fisico, se c'è
    filepath = DOCS_DIR / doc["filename"]
    try:
        filepath.unlink(missing_ok=True)  # Py ≥3.8
    except Exception as exc:
        print(f"[WARN] impossibile cancellare file: {exc}")

    await docs_coll.delete_one({"_id": doc["_id"]})
    return Response(status_code=200, media_type="text/plain")

# ---- DOWNLOAD SICURO -----------------------------------------------

@app.get("/doc/{doc_id}")
async def download_document(
    doc_id: str,
    user = Depends(get_current_user),
    docs_coll: AsyncIOMotorCollection = Depends(get_docs_coll)
):
    """Restituisce il PDF se l'utente ha diritto di vederlo."""
    doc = await docs_coll.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Documento non trovato")

    # regole di autorizzazione
    if user["role"] != "admin" and doc["branch"] not in ("*", user["branch"]):
        raise HTTPException(403, "Non autorizzato")

    filepath = DOCS_DIR / doc["filename"]
    if not filepath.exists():
        raise HTTPException(404, "File mancante sul server")

    return FileResponse(
        path=filepath,
        media_type="application/pdf",
        filename=f"{doc['title']}.pdf"
    )

@app.get("/doc/{doc_id}/preview")
async def preview_document(
    doc_id: str,
    user = Depends(get_current_user),
    docs_coll: AsyncIOMotorCollection = Depends(get_docs_coll)
):
    doc = await docs_coll.find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Documento non trovato")

    if user["role"] != "admin" and doc["branch"] not in ("*", user["branch"]):
        raise HTTPException(403, "Non autorizzato")

    filepath = BASE_DOCS_DIR / doc["filename"]
    if not filepath.exists():
        raise HTTPException(404, "File mancante")

    return FileResponse(
        path=filepath,
        media_type="application/pdf",
        filename=f"{doc['title']}.pdf",
        headers={"Content-Disposition": "inline"}
    )


# ---- DEPENDENCY: collection link utili branch/role aware ------------

async def get_links_coll(
    user = Depends(get_current_user),
    db   = Depends(get_db)
) -> AsyncIOMotorCollection:
    """Collection 'links' filtrata per branch/role quando necessario."""
    coll = db.links
    if user["role"] == "admin":
        return coll
    return coll.with_options()   # filtro applicato nella query rotta

# -------------------------------------------------------------------- 
#                            LINK  UTILI                             
# -------------------------------------------------------------------- 

@app.get("/links", response_class=HTMLResponse)
async def links_page(
    request: Request,
    links_coll: AsyncIOMotorCollection = Depends(get_links_coll),
    q: str | None = Query(None, description="search text"),
):
    user = request.state.user
    base_filter: dict = {}

    if user["role"] != "admin":
        base_filter = {
            "$and": [
                {"$or": [{"branch": "*"}, {"branch": user["branch"]}]},
                {"$or": [{"role": "*"}, {"role": "staff"}]},
            ]
        }

    # filtro ricerca testo su titolo o tag
    if q:
        regex = {"$regex": q, "$options": "i"}
        text_filter = {"$or": [{"title": regex}, {"tags": regex}]}
        base_filter = {"$and": [base_filter, text_filter]} if base_filter else text_filter

    links = await links_coll.find(base_filter).sort("order", 1).to_list(length=None)

    # --- Segna tutte le notifiche 'link' come lette per l'utente ---
    user_id = str(user["_id"])
    result = await request.app.state.db.notifiche.update_many(
        {"tipo": "link", "letta_da": {"$ne": user_id}},
        {"$push": {"letta_da": user_id}}
    )
    print("Notifiche link segnate come lette:", result.modified_count)

    return templates.TemplateResponse(
        "links/links_index.html",
        {"request": request, "links": links, "current_user": user, "query": q or ""}
    )


# ---- NUOVO LINK (solo admin) ---------------------------------------

# (RIMOSSO: tutte le route /links/* duplicate, ora gestite in app/links.py)

# ---- EDIT / DELETE link ( solo admin ) ------------------------------

# (RIMOSSO: tutte le route /links/* duplicate, ora gestite in app/links.py)

# --------------------------- NEWS ---------------------------

@app.get("/news", response_class=HTMLResponse)
async def news_page(
    request: Request,
    db=Depends(get_db),
    user=Depends(get_current_user)
):
    coll = db.news
    mongo_filter = {} if user["role"] == "admin" else {
        "$or": [
            {"branch": "*"},
            {"branch": user["branch"]}
        ]
    }

    news_items = [to_str_id(n) for n in await coll.find(mongo_filter).sort("created_at", -1).to_list(None)]

    return templates.TemplateResponse(
        "news/news_index.html",
        {"request": request, "user": user, "news": news_items}
    )


@app.get("/news/new", response_class=HTMLResponse,
         dependencies=[Depends(require_admin)])
async def new_news_form(request: Request):
    return templates.TemplateResponse("news/news_new.html", {"request": request})


@app.post("/news/new", response_class=RedirectResponse,
          status_code=303,
          dependencies=[Depends(require_admin)])
async def create_news(
    request: Request,
    db=Depends(get_db),
    title: str = Form(...),
    content: str = Form(...),
    branch: str = Form(...)
):
    await db.news.insert_one({
        "title": title.strip(),
        "content": content.strip(),
        "branch": branch.strip(),
        "created_at": datetime.utcnow()
    })
    return RedirectResponse("/news", status_code=303)


@app.get("/news/{news_id}/edit", response_class=HTMLResponse,
         dependencies=[Depends(require_admin)])
async def edit_news_form(request: Request, news_id: str, db=Depends(get_db)):
    news = await db.news.find_one({"_id": ObjectId(news_id)})
    if not news:
        raise HTTPException(404, "News non trovata")
    return templates.TemplateResponse("news/news_edit_partial.html", {"request": request, "n": to_str_id(news)})


@app.post("/news/{news_id}/edit", response_class=HTMLResponse,
          dependencies=[Depends(require_admin)])
async def edit_news_submit(
    request: Request, news_id: str, db=Depends(get_db),
    title: str = Form(...),
    content: str = Form(...),
    branch: str = Form(...)
):
    await db.news.update_one(
        {"_id": ObjectId(news_id)},
        {"$set": {
            "title": title.strip(),
            "content": content.strip(),
            "branch": branch.strip()
        }}
    )
    updated = await db.news.find_one({"_id": ObjectId(news_id)})
    resp = templates.TemplateResponse(
    "news/news_row_partial.html",
    {"request": request, "n": to_str_id(updated), "user": request.state.user}
)

    resp.headers["HX-Trigger"] = "closeModal"
    return resp


@app.delete("/news/{news_id}", status_code=200,
            dependencies=[Depends(require_admin)])
async def delete_news(news_id: str, db=Depends(get_db)):
    await db.news.delete_one({"_id": ObjectId(news_id)})
    return Response(status_code=200)




# --------------------------- contatti ---------------------------
# (Gestione spostata in app/contatti.py, rimuovere le route duplicate qui)
# Tutte le route /contatti/* sono ora gestite dal router contatti_router.

# ---- FOTO PROFILO ------------------------------------------------

from PIL import Image
import io

@app.post("/me/foto")
async def upload_foto(
    request: Request,
    file: UploadFile = File(...),      # ora è obbligatorio
    user = Depends(get_current_user),
    _ = Depends(validate_csrf)         # protezione CSRF
):
    # Leggi contenuto del file
    contents = await file.read()

    # Controlli sul file
    MAX_SIZE = 2 * 1024 * 1024          # 2 MB
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Formato non supportato")
    if len(contents) > MAX_SIZE:
        raise HTTPException(400, "L'immagine supera 2 MB")

    try:
        # Apri l'immagine con Pillow
        img = Image.open(io.BytesIO(contents))
        rgb_img = img.convert("RGB")  # Converti in RGB se PNG con trasparenza

        # Salva sempre come JPG
        path = FOTO_DIR / f"{user['_id']}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        rgb_img.save(path, format="JPEG", quality=85)

        # Aggiorna il campo avatar nel documento utente
        db = request.app.state.db
        avatar_url = f"/media/foto/{user['_id']}.jpg"
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"avatar": avatar_url}})

        print("✅ Foto convertita e salvata come JPG:", path)
        resp = RedirectResponse("/me", status_code=303)
        resp.headers["Cache-Control"] = "no-store"  # previene caching
        return resp

    except Exception as e:
        print("❌ Errore durante la conversione:", e)
        raise HTTPException(400, "Immagine non valida")

@app.post("/me/foto/delete")
async def delete_foto(
    request: Request,
    user = Depends(get_current_user)
):
    # Cerca tutti i file possibili (jpg, jpeg, png)
    for ext in ("jpg", "jpeg", "png"):
        path = FOTO_DIR / f"{user['_id']}.{ext}"
        if path.exists():
            path.unlink()
            break
    resp = RedirectResponse("/me", status_code=303)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
    





from fastapi.routing import APIRoute

def stampa_route_registrate():
    print("\n📋 ROUTE REGISTRATE:")
    for route in app.routes:
        if isinstance(route, APIRoute):
            metodi = ",".join(route.methods)
            print(f"{metodi:10} {route.path}")

stampa_route_registrate()  # <--- assicurati che questa riga CI SIA

@app.exception_handler(HTTPException)
async def htmx_auth_handler(request: Request, exc: HTTPException):
    """
    • Se è una richiesta **normale** e arriva 401 → redirect al /login.
    • Se è una richiesta **HTMX** restituiamo 401 + header HX-Redirect
      SENZA rilanciare l'eccezione, così Starlette conclude il ciclo
      invece di far crashare il TaskGroup.
    """
    if exc.status_code == 401:
        # --- chiamata browser classica ---------------------------------
        if "HX-Request" not in request.headers:
            target = exc.headers.get("HX-Redirect", "/login")
            return RedirectResponse(target, status_code=302)

        # --- chiamata HTMX --------------------------------------------
        # Rispondiamo con lo stesso 401 e gli header originali
        # (HTMX leggerà HX-Redirect e farà il redirect "pulito")
        return Response(status_code=401, headers=exc.headers)

    # Lascia invariati gli altri status (404, 403, ecc.)
    return Response(status_code=exc.status_code, headers=exc.headers)

@app.get("/messaggi", response_class=HTMLResponse)
async def messaggi_page(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "messaggi.html",
        {"request": request, "user": user}
    )


async def _current_user(request: Request, db=Depends(get_db)):
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="login richiesto")
    return await db.users.find_one({"_id": ObjectId(uid)})

@app.post("/api/me/pins")
async def add_pin(item: dict, request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    # item = {"type": "ai_news", "id": "123"}
    if not item or "type" not in item or "id" not in item:
        raise HTTPException(status_code=400, detail="Invalid item")
    # Forza id a stringa
    item = {"type": item["type"], "id": str(item["id"])}
    
    # Aggiorna il documento dell'utente
    updated_user = await db.users.find_one_and_update(
        {"_id": user["_id"]},
        {"$addToSet": {"pinned_items": item}},
        return_document=True
    )

    # aggiorna la copia in sessione, così resta dopo il refresh
    request.session["pinned_items"] = updated_user["pinned_items"]
    
    print("DEBUG - Session after pin:", request.session["pinned_items"])  # Debug log
    print("DEBUG - Updated user pinned_items:", updated_user["pinned_items"])  # Debug log

    # broadcast
    await broadcast_resource_event(
        "pin/add",
        item_type=item["type"],
        item_id=item["id"],
        user_id=str(user["_id"])
    )
    return Response(status_code=204)

@app.delete("/api/me/pins/{item_type}/{item_id}")
async def remove_pin(item_type: str, item_id: str, request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    
    # Aggiorna il documento dell'utente
    updated_user = await db.users.find_one_and_update(
        {"_id": user["_id"]},
        {"$pull": {"pinned_items": {"type": item_type, "id": str(item_id)}}},
        return_document=True
    )

    # aggiorna la copia in sessione, così resta dopo il refresh
    request.session["pinned_items"] = updated_user["pinned_items"]
    
    print("DEBUG - Session after unpin:", request.session["pinned_items"])  # Debug log
    print("DEBUG - Updated user pinned_items:", updated_user["pinned_items"])  # Debug log

    # broadcast
    await broadcast_resource_event(
        "pin/remove",
        item_type=item_type,
        item_id=item_id,
        user_id=str(user["_id"])
    )
    return Response(status_code=204)


# --------------------------- DEBUG TOOLS -------------------------------

def signer_debug(secret, salt):
    """
    Debug helper per verificare i parametri di firma
    """
    ser = URLSafeSerializer(secret, salt=salt)
    signer = ser.make_signer(salt)
    logger.debug("=== SIGNER DEBUG ===")
    logger.debug("key_derivation: %s", signer.key_derivation)
    logger.debug("digest_method : %s", signer.digest_method().name)
    logger.debug("salt         : %s", signer.salt)
    logger.debug("secret       : %s", secret)  # Mostro l'intera chiave

# --------------------------- STARTUP --------------------------------

@app.on_event("startup")
async def startup():
    """
    Inizializzazione dell'applicazione
    """
    # Debug del percorso .env e della chiave di sessione
    logger.debug("=== ENV DEBUG ===")
    logger.debug("SESSION_SECRET = %s", os.environ.get("SESSION_SECRET"))  # Mostro l'intera chiave
    logger.debug(".env path      = %s", Path('.env').resolve())
    
    # Debug dei parametri del signer
    signer_debug(SECRET_KEY, "starlette.sessions")

@app.get("/home/highlights/{type}/partial")
async def get_type_section(type: str, request: Request, user=Depends(get_current_user)):
    """Restituisce solo la sezione specifica per tipo"""
    highlights = await get_all_highlights(request)
    filtered_highlights = [h for h in highlights if h["type"] == type]
    return templates.TemplateResponse(
        f"partials/home_{type}.html",
        {
            "request": request,
            "user": user,
            "highlights": filtered_highlights,
            "pinned": user.get("pinned_items", [])
        }
    )

@app.on_event("startup")
async def regen_secret_if_dev():
    if os.getenv("DEV_MODE"):
        print("DEV MODE: Regenerating secret key...")
        os.environ["SESSION_SECRET"] = secrets.token_urlsafe(32)

# Endpoint WebSocket principale
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_main(websocket)

# Serve favicon.ico
@app.get('/favicon.ico')
async def favicon():
    return FileResponse('static/img/Logo_HQ.png')

