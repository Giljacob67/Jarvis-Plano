from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas import NotImplementedResponse

router = APIRouter()


@router.get("/google/start", response_model=NotImplementedResponse, status_code=501)
async def google_auth_start() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=NotImplementedResponse(
            message="Google OAuth flow not implemented yet. Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first."
        ).model_dump(),
    )


@router.get("/google/callback", response_model=NotImplementedResponse, status_code=501)
async def google_auth_callback() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=NotImplementedResponse(
            message="Google OAuth callback not implemented yet."
        ).model_dump(),
    )
