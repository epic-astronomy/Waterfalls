from fastapi import APIRouter, Request

from app.core.auth import current_user

router = APIRouter()


@router.get("/me")
def me(request: Request):
    """The signed-in user's email and role, for the page header and menus"""
    user = current_user(request)
    if not user:
        return dict(signed_in=False)
    return dict(signed_in=True, email=user["email"], role=user["role"])
