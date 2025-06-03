from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from app.deps import require_admin, get_current_user
from app.utils.save_with_notifica import save_and_notify
from app.models.news_model import NewsIn, NewsOut
from datetime import datetime
from bson import ObjectId
from fastapi import status
from app.constants import DEFAULT_HIRE_TYPES
from app.notifiche import crea_notifica

news_router = APIRouter(tags=["news"])

@news_router.post(
    "/news/new",
    status_code=303,
    response_class=RedirectResponse,
    dependencies=[Depends(require_admin)]
)
async def create_news(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    branch: str = Form(...),
    employment_type: str = Form("*"),
    show_on_home: str = Form(None)
):
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    result = await save_and_notify(
        request=request,
        collection="news",
        payload={
            "title": title.strip(),
            "content": content.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list
        },
        tipo="news",
        titolo=title.strip(),
        branch=branch.strip()
    )
    
    if request.headers.get("HX-Request"):
        # Recupera la news appena creata
        db = request.app.state.db
        news = await db.news.find_one({"title": title.strip(), "content": content.strip()})
        response = request.app.state.templates.TemplateResponse(
            "news/news_row_partial.html",
            {"request": request, "n": news, "user": request.state.user}
        )
        response.headers["HX-Trigger"] = "closeModal"
        return response
    
    return RedirectResponse("/news", status_code=303)

@news_router.get("/news", response_class=HTMLResponse)
async def list_news(
    request: Request,
    current_user = Depends(get_current_user)
):
    db = request.app.state.db
    employment_type = current_user.get("employment_type")
    if current_user["role"] == "admin" or not employment_type:
        mongo_filter = {}
    else:
        mongo_filter = {
            "$or": [
                {"employment_type": {"$exists": False}},
                {"employment_type": {"$size": 0}},
                {"employment_type": {"$in": [employment_type]}}
            ]
        }
    news_items = await db.news.find(mongo_filter).sort("created_at", -1).to_list(None)
    return request.app.state.templates.TemplateResponse(
        "news/news_index.html",
        {
            "request": request,
            "news": news_items,
            "current_user": current_user
        }
    )

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
    employment_type: str = Form("*")
):
    db = request.app.state.db
    employment_type_list = [employment_type] if isinstance(employment_type, str) else (employment_type or [])
    await db.news.update_one(
        {"_id": ObjectId(news_id)},
        {"$set": {
            "title": title.strip(),
            "content": content.strip(),
            "branch": branch.strip(),
            "employment_type": employment_type_list
        }}
    )
    updated = await db.news.find_one({"_id": ObjectId(news_id)})
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

@news_router.delete(
    "/news/{news_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)]
)
async def delete_news(
    request: Request,
    news_id: str,
    user = Depends(get_current_user)
):
    db = request.app.state.db
    await db.news.delete_one({"_id": ObjectId(news_id)})
    await db.home_highlights.delete_one({"type": "news", "object_id": ObjectId(news_id)})
    return PlainTextResponse("")
