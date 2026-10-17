from fastapi import APIRouter

from app.api.routes import watchlist
from app.api.routes import imaging
from app.api.routes import frb
from app.api.routes import skymon

api_router = APIRouter()
api_router.include_router(watchlist.router, tags=["watchlist"],prefix="/watchlist")
api_router.include_router(imaging.router, tags=["imaging"],prefix="/imaging")
api_router.include_router(frb.router, tags=["frb"], prefix="/frb")
api_router.include_router(skymon.router, tags=["skymon"], prefix="/skymon")
