from fastapi import APIRouter

from app.api.routes import watchlist
from app.api.routes import imaging

api_router = APIRouter()
api_router.include_router(watchlist.router, tags=["watchlist"],prefix="/watchlist")
api_router.include_router(imaging.router, tags=["imaging"],prefix="/imaging")