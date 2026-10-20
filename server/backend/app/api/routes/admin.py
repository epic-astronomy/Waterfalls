"""
User management for admins: the invited users of the Hanko login, their
roles, invitations and removal. Every route needs an admin (see main.py).
An admin cannot change their own role or remove themselves, so the site is
never left without one.
"""
import logging
import re
import smtplib
import ssl
import urllib.error
import urllib.parse
from email.message import EmailMessage

from fastapi import APIRouter, Body, HTTPException, Request

from app.core.auth import ROLES, admin_api, forget, primary_email, role_of
from app.core.config import settings

router = APIRouter()
log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hanko(method: str, path: str, body: dict | None = None):
    try:
        return admin_api(method, path, body)
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=502 if e.code >= 500 else e.code,
                            detail=f"the login service refused it ({e.code})")
    except Exception:
        raise HTTPException(status_code=503, detail="the login service did not answer")


def _user_row(u: dict) -> dict:
    return dict(id=u["id"], email=primary_email(u), role=role_of(u), created_at=u.get("created_at"))


@router.get("/users")
def users():
    """Every user with their role, newest first"""
    out, page = [], 1
    while True:
        batch = _hanko("GET", f"/users?page={page}&per_page=100&sort_direction=desc") or []
        out += batch
        if len(batch) < 100:
            break
        page += 1
    # the list leaves out the metadata, so each user is read for its role
    return [_user_row(_hanko("GET", f"/users/{u['id']}")) for u in out]


def _send_invitation(email: str, role: str, by: str) -> bool:
    if not settings.emails_enabled:
        return False
    msg = EmailMessage()
    msg["Subject"] = "Your invitation to EPIC Astronomy"
    msg["From"] = f"{settings.EMAILS_FROM_NAME or 'EPIC Astronomy'} <{settings.EMAILS_FROM_EMAIL}>"
    msg["To"] = email
    what = "the all-sky monitor, its catalogue and the review of its candidates, and the user list" \
        if role == "admin" else "the data of the EPIC Waterfalls website"
    msg.set_content(
        f"Hello,\n\n{by} has invited you to EPIC Astronomy, with access to {what}.\n\n"
        f"Sign in at {settings.WEBSITE_LOGIN_URL} with this email address ({email}). "
        "There is no password: a code is sent to this address each time you sign in, "
        "and you can add a passkey afterwards.\n\nEPIC Astronomy\nhttps://epic-astronomy.org\n")
    try:
        if settings.SMTP_SSL:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
            if settings.SMTP_TLS:
                server.starttls(context=ssl.create_default_context())
        with server:
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
            server.send_message(msg)
        return True
    except Exception as e:
        log.warning("invitation to %s not sent: %s", email, e)
        return False


@router.post("/users")
def invite(request: Request, email: str = Body(..., max_length=200), role: str = Body(...),
           notify: bool = Body(True)):
    """Create an account for an email address with a role, and send an invitation"""
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="not an email address")
    if role not in ROLES:
        raise HTTPException(status_code=422, detail="unknown role")
    if _hanko("GET", f"/users?email={urllib.parse.quote(email)}"):
        raise HTTPException(status_code=409, detail="this address already has an account")
    u = _hanko("POST", "/users", dict(emails=[dict(address=email, is_primary=True, is_verified=True)]))
    _hanko("PATCH", f"/users/{u['id']}/metadata", dict(private_metadata=dict(role=role)))
    sent = _send_invitation(email, role, request.state.user["email"]) if notify else False
    return dict(user=_user_row(_hanko("GET", f"/users/{u['id']}")), invited=sent)


@router.patch("/users/{uid}")
def set_role(uid: str, request: Request, role: str = Body(..., embed=True)):
    if role not in ROLES:
        raise HTTPException(status_code=422, detail="unknown role")
    if uid == request.state.user["id"]:
        raise HTTPException(status_code=409, detail="you cannot change your own role")
    _hanko("PATCH", f"/users/{uid}/metadata", dict(private_metadata=dict(role=role)))
    forget(uid)
    return _user_row(_hanko("GET", f"/users/{uid}"))


@router.delete("/users/{uid}")
def remove(uid: str, request: Request):
    if uid == request.state.user["id"]:
        raise HTTPException(status_code=409, detail="you cannot remove yourself")
    _hanko("DELETE", f"/users/{uid}")
    forget(uid)
    return dict(removed=uid)
