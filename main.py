# ---------------------------- IMPORT ---------------------------------
import os, secrets
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Literal, Dict
from datetime import date, datetime
from bson import ObjectId    
from app.news import news_router
from app.links import links_router
from app.documents import documents_router, BASE_DOCS_DIR
from app.contatti import contatti_router
from app.deps import require_admin, get_current_user           # updated import

from dotenv import load_dotenv
import motor.motor_asyncio
from bson import ObjectId
from passlib.hash import bcrypt
from pydantic import BaseModel, Field

from fastapi import (
    FastAPI, Request, Depends, HTTPException,
    Form, Response, APIRouter, status,
    UploadFile, File, Query, WebSocket, WebSocketDisconnect               # ← aggiunto Query
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

# --- LOGGING ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,                       # passa a DEBUG se vuoi più dettaglio
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("intranet")


# --------------------------- CONFIG ----------------------------------
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/intranet")

limiter   = Limiter(key_func=get_remote_address)
templates = Jinja2Templates(directory="templates")
templates.env.globals["datetime"] = datetime

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

templates.env.filters["markdown"] = markdown_filter
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

# Crea l'app e assegna templates
app = FastAPI(lifespan=lifespan)
app.state.templates = templates

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")  # 👈 AGGIUNGI QUESTA

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", secrets.token_urlsafe(32)),
    same_site="lax",
    https_only=False,  # 👈 disattiva il blocco su HTTP
)

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


# --------------------------- ROUTE UI --------------------------------
from fastapi.responses import RedirectResponse

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user = Depends(get_current_user)):
    db = request.app.state.db
    
    # Recupera gli highlights filtrati per branch e hire_type
    highlights = await db.home_highlights.find().to_list(length=None)
    print("[DEBUG HOME] highlights trovati in home_highlights:")
    for h in highlights:
        print(f"  - {h}")
    filtered_highlights = []
    
    # Safe access to user properties with fallbacks
    emp_type_user = user.get("employment_type")  # None se mancante
    branch_user = user.get("branch")             # None se mancante
    
    for h in highlights:
        if h["type"] == "document":
            doc = await db.documents.find_one({"_id": h["object_id"]})
            if not doc:
                continue
            if (h["branch"] in ("*", branch_user)) and ("*" in h["employment_type"] or emp_type_user in h["employment_type"]):
                filtered_highlights.append(h)
        elif h["type"] == "ai_news":
            doc = await db.ai_news.find_one({"_id": h["object_id"]})
            if not doc:
                continue
            if (h["branch"] in ("*", branch_user)) and ("*" in h["employment_type"] or emp_type_user in h["employment_type"]):
                filtered_highlights.append(h)
        elif h["type"] == "news":
            news = await db.news.find_one({"_id": h["object_id"]})
            if not news:
                continue
            if (h["branch"] in ("*", branch_user)) and ("*" in h.get("employment_type", ["*"]) or emp_type_user in h.get("employment_type", ["*"])):
                filtered_highlights.append(h)
        elif h["type"] == "link":
            link = await db.links.find_one({"_id": h["object_id"]})
            if not link:
                continue
            if (h["branch"] in ("*", branch_user)) and ("*" in h["employment_type"] or emp_type_user in h["employment_type"]):
                filtered_highlights.append(h)
        elif h["type"] == "contact":
            contact = await db.contatti.find_one({"_id": h["object_id"]})
            if not contact:
                continue
            if (h["branch"] in ("*", branch_user)) and ("*" in h["employment_type"] or emp_type_user in h["employment_type"]):
                filtered_highlights.append(h)
    filtered_highlights.sort(key=lambda x: x["created_at"], reverse=True)
    print("[DEBUG HOME] filtered_highlights finali:")
    for fh in filtered_highlights:
        print(f"  - {fh}")

    # Recupera tutte le news (senza limiti)
    news = await db.news.find().sort("created_at", -1).to_list(length=None)
    
    # --- Conteggio notifiche non lette di tipo documento ---
    user_id = str(user["_id"])
    emp_type_user = user.get("employment_type")
    branch_user = user.get("branch")
    notifica_doc_filter = {
        "tipo": "documento",
        "letta_da": {"$ne": user_id},
        "$or": [
            {"employment_type": {"$in": [emp_type_user, "*"]}},
            {"employment_type": emp_type_user},
            {"employment_type": "*"},
            {"employment_type": {"$exists": False}}
        ],
        "branch": {"$in": [branch_user, "*"]}
    }
    new_docs_count = await db.notifiche.count_documents(notifica_doc_filter)
    print("Nuove notifiche non lette:", new_docs_count)

    # --- Notifiche NEWS ---
    new_news_count = await db.notifiche.count_documents({
        "tipo": "news",
        "letta_da": {"$ne": user_id}
    })

    # --- Notifiche LINK ---
    notifica_link_filter = {
        "tipo": "link",
        "letta_da": {"$ne": user_id},
        "$or": [
            {"employment_type": {"$in": [emp_type_user, "*"]}},
            {"employment_type": emp_type_user},
            {"employment_type": "*"},
            {"employment_type": {"$exists": False}}
        ],
        "branch": {"$in": [branch_user, "*"]}
    }
    new_links_count = await db.notifiche.count_documents(notifica_link_filter)

    # --- Notifiche CONTATTI ---
    notifica_contatti_filter = {
        "tipo": "contatto",
        "letta_da": {"$ne": user_id},
        "$or": [
            {"employment_type": {"$in": [emp_type_user, "*"]}},
            {"employment_type": emp_type_user},
            {"employment_type": "*"},
            {"employment_type": {"$exists": False}}
        ],
        "branch": {"$in": [branch_user, "*"]}
    }
    new_contacts_count = await db.notifiche.count_documents(notifica_contatti_filter)

    # PATCH: Valorizzo unread_counts per il badge, sempre presente
    unread_counts = {"link": new_links_count if 'new_links_count' in locals() else 0}

    print("[DEBUG HOME] user._id:", user.get("_id"))
    print("[DEBUG HOME] user.pinned_items:", user.get("pinned_items"))

    return request.app.state.templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "highlights": filtered_highlights,
            "news": news,
            "new_docs_count": new_docs_count,
            "new_news_count": new_news_count,
            "new_links_count": new_links_count,
            "new_contacts_count": new_contacts_count,
            "unread_counts": unread_counts,
        }
    )

@app.get("/home/highlights/partial", response_class=HTMLResponse)
async def home_highlights_partial(request: Request, user = Depends(get_current_user)):
    db = request.app.state.db
    print(f"[REALTIME][HIGHLIGHTS] user_id={user.get('_id')}, branch={user.get('branch')}, employment_type={user.get('employment_type')}")
    highlights = await db.home_highlights.find().to_list(length=None)
    print(f"[REALTIME][HIGHLIGHTS] highlights in home_highlights: {[str(h) for h in highlights]}")
    filtered_highlights = []
    emp_type_user = user.get("employment_type")
    branch_user = user.get("branch")
    for h in highlights:
        print(f"[LOG] PROCESSO highlight: {h}")
        branch_h = h.get("branch", "*")
        emp_type_h = h.get("employment_type", ["*"])
        print(f"[LOG] Filtro highlight: branch_h={branch_h}, emp_type_h={emp_type_h}, branch_user={branch_user}, emp_type_user={emp_type_user}")
        passa_filtro = (branch_h in (branch_user, "*", "Tutte") or branch_user in (None, "*", "Tutte")) and (
            emp_type_user is None or
            "*" in emp_type_h or 
            emp_type_user in emp_type_h or 
            emp_type_user == "*"
        )
        print(f"[LOG] Risultato filtro: {passa_filtro}")
        if passa_filtro:
            if h["type"] == "document":
                doc = await db.documents.find_one({"_id": h["object_id"]})
                print(f"[LOG] Documento associato: {doc}")
                if not doc:
                    continue
                filtered_highlights.append({
                    "type": "document",
                    "id": str(doc["_id"]),
                    "title": doc["title"],
                    "filename": doc.get("filename", ""),
                    "created_at": h["created_at"]
                })
            elif h["type"] == "ai_news":
                doc = await db.ai_news.find_one({"_id": h["object_id"]})
                print(f"[LOG] AI News associata: {doc}")
                if not doc:
                    continue
                filtered_highlights.append({
                    "type": "ai_news",
                    "id": str(doc["_id"]),
                    "title": doc["title"],
                    "filename": doc.get("filename", ""),
                    "external_url": doc.get("external_url", ""),
                    "created_at": h["created_at"]
                })
            elif h["type"] == "link":
                link = await db.links.find_one({"_id": h["object_id"]})
                print(f"[LOG] Link associato: {link}")
                if not link:
                    continue
                filtered_highlights.append({
                    "type": "link",
                    "id": str(link["_id"]),
                    "title": link["title"],
                    "url": link["url"],
                    "created_at": h["created_at"]
                })
            elif h["type"] == "contact":
                contact = await db.contatti.find_one({"_id": h["object_id"]})
                print(f"[LOG] Contatto associato: {contact}")
                if not contact:
                    continue
                filtered_highlights.append({
                    "type": "contact",
                    "id": str(contact["_id"]),
                    "title": contact["name"],
                    "branch": contact["branch"],
                    "role": contact.get("role", ""),
                    "employment_type": contact.get("employment_type", []),
                    "created_at": h["created_at"],
                    "email": contact.get("email", ""),
                    "phone": contact.get("phone", ""),
                    "bu": contact.get("bu", ""),
                    "team": contact.get("team", ""),
                    "work_branch": contact.get("work_branch", "")
                })
            elif h["type"] == "news":
                news = await db.news.find_one({"_id": h["object_id"]})
                print(f"[LOG] News associata: {news}")
                if not news:
                    continue
                filtered_highlights.append({
                    "type": "news",
                    "id": str(news["_id"]),
                    "title": news["title"],
                    "created_at": h["created_at"],
                    "branch": news.get("branch", ""),
                    "employment_type": news.get("employment_type", []),
                    "content": news.get("content", "")
                })
    print(f"[LOG] Lista finale filtered_highlights: {filtered_highlights}")
    filtered_highlights.sort(key=lambda x: x["created_at"], reverse=True)
    print("[DEBUG PARTIAL] Highlights restituiti:", filtered_highlights)
    print("[DEBUG PARTIAL] user._id:", user.get("_id"))
    print("[DEBUG PARTIAL] user.pinned_items:", user.get("pinned_items"))

    # Aggiorna i pin direttamente dal DB utente per avere la lista aggiornata
    user_db = await db.users.find_one({"_id": user["_id"]})
    user["pinned_items"] = user_db.get("pinned_items", [])
    print("[LOG][ULTIMO] Tutti gli highlights in home_highlights:", highlights)
    print("[LOG][ULTIMO] Lista finale filtered_highlights:", filtered_highlights)
    for h in highlights:
        if h["type"] == "news":
            news = await db.news.find_one({"_id": h["object_id"]})
            print(f"[LOG][ULTIMO] News collegata a highlight {h.get('title', '')}: {news}")
    return request.app.state.templates.TemplateResponse(
        "partials/home_highlights.html",
        {"request": request, "highlights": filtered_highlights, "user": user}
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
    request.session.clear()
    resp = RedirectResponse("/login", 302)
    resp.delete_cookie("session")
    return resp

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
async def upload_form(request: Request):
    template = "documents/upload_partial.html" if request.headers.get("hx-request") == "true" else "documents/upload.html"
    return templates.TemplateResponse(template, {"request": request})

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
        "links.html",
        {"request": request, "links": links, "user": user, "query": q or ""}
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
    
from app.notifiche import notifiche_router
app.include_router(notifiche_router)





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

from app.organigramma import organigramma_router
app.include_router(organigramma_router)

from app.ws_broadcast import websocket_notify
app.add_api_websocket_route("/ws/notify", websocket_notify)

from app.soci import soci_router
app.include_router(soci_router)

from app.ai_news import ai_news_router
app.include_router(ai_news_router)

@app.post("/api/me/pins")
async def add_pin(item: dict, request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    # item = {"type": "ai_news", "id": "123"}
    if not item or "type" not in item or "id" not in item:
        raise HTTPException(status_code=400, detail="Invalid item")
    # Forza id a stringa
    item = {"type": item["type"], "id": str(item["id"])}
    pinned = user.get("pinned_items", [])
    if item not in pinned:
        pinned.append(item)
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"pinned_items": pinned}})
        if "user" in request.session:
            request.session["user"]["pinned_items"] = pinned
    return JSONResponse(content={"ok": True, "pinned_items": pinned})

@app.delete("/api/me/pins/{item_type}/{item_id}")
async def remove_pin(item_type: str, item_id: str, request: Request, user=Depends(get_current_user)):
    db = request.app.state.db
    pinned = user.get("pinned_items", [])
    # Confronta sempre id come stringa
    new_pinned = [i for i in pinned if not (i["type"] == item_type and i["id"] == str(item_id))]
    if len(new_pinned) != len(pinned):
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"pinned_items": new_pinned}})
        if "user" in request.session:
            request.session["user"]["pinned_items"] = new_pinned
    return JSONResponse(content={"ok": True, "pinned_items": new_pinned})

@app.websocket("/ws/notify")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_notify(websocket)

