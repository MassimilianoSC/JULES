from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.deps import get_current_user

organigramma_router = APIRouter()

@organigramma_router.get("/organigramma", response_class=HTMLResponse)
async def organigramma_page(request: Request, user=Depends(get_current_user)):
    return request.app.state.templates.TemplateResponse(
        "organigramma.html",
        {"request": request, "user": user}
    ) 