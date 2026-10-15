from fastapi import APIRouter

from app.api.routes import watchlist
from app.api.routes import imaging
from app.api.routes import frb

api_router = APIRouter()
api_router.include_router(watchlist.router, tags=["watchlist"],prefix="/watchlist")
api_router.include_router(imaging.router, tags=["imaging"],prefix="/imaging")
api_router.include_router(frb.router, tags=["frb"], prefix="/frb")
