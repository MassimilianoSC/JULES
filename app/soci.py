from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.deps import require_admin, get_current_user

soci_router = APIRouter()

@soci_router.get("/soci", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def soci_page(request: Request, user=Depends(get_current_user)):
    return request.app.state.templates.TemplateResponse(
        "soci.html",
        {"request": request, "user": user}
    ) 