from fastapi import APIRouter, Depends

from app.api.routes import watchlist
from app.api.routes import imaging
from app.api.routes import frb
from app.api.routes import skymon
from app.api.routes import account
from app.api.routes import admin
from app.core.auth import require_admin

api_router = APIRouter()
api_router.include_router(watchlist.router, tags=["watchlist"],prefix="/watchlist")
api_router.include_router(imaging.router, tags=["imaging"],prefix="/imaging")
api_router.include_router(frb.router, tags=["frb"], prefix="/frb")
# the all-sky monitor and its catalogue are for admins only, as is the user list
api_router.include_router(skymon.router, tags=["skymon"], prefix="/skymon", dependencies=[Depends(require_admin)])
api_router.include_router(account.router, tags=["auth"], prefix="/auth")
api_router.include_router(admin.router, tags=["admin"], prefix="/admin", dependencies=[Depends(require_admin)])
