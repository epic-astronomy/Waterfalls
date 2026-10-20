"""
Who is signed in, and with which role.

The session token comes from the "hanko" cookie, which Hanko sets for the
whole domain, or from an Authorization header. It is checked with Hanko's
public API (GET /me answers only for a valid session), and the user's email
and role are read from the admin API, which listens on the head node only.
Roles are kept in the user's private metadata, which the user cannot change:
"admin" (the all-sky monitor, its catalogue, reviews and the user list) or
"member". Answers are cached briefly, so a page's many requests cost one
check; a role change applies within ROLE_CACHE_S.
"""
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request

from fastapi import HTTPException, Request

from app.core.config import settings

ROLES = ("admin", "member")
ROLE_CACHE_S = 60.0

_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()


def _get(url: str, token: str | None = None, timeout: float = 5.0):
    hdr = {"Accept": "application/json"}
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
        return json.loads(r.read())


def admin_api(method: str, path: str, body: dict | None = None, timeout: float = 5.0):
    """A call to Hanko's admin API; returns the decoded answer (None if empty)"""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(settings.HANKO_ADMIN_URL.rstrip("/") + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def primary_email(user: dict) -> str:
    emails = user.get("emails") or []
    return next((e["address"] for e in emails if e.get("is_primary")), emails[0]["address"] if emails else "")


def role_of(user: dict) -> str | None:
    role = ((user.get("metadata") or {}).get("private_metadata") or {}).get("role")
    return role if role in ROLES else None


def _token(request: Request) -> str:
    return request.cookies.get("hanko") or \
        request.headers.get("authorization", "").removeprefix("Bearer ").strip()


def forget(user_id: str | None = None):
    """Drop cached sessions (of one user, or all), after a role change"""
    with _lock:
        for k in [k for k, (_, u) in _cache.items() if user_id is None or (u and u["id"] == user_id)]:
            del _cache[k]


def current_user(request: Request) -> dict | None:
    """{id, email, role} of the signed-in user, or None"""
    token = _token(request)
    if not token:
        return None
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ROLE_CACHE_S:
            return hit[1]
    try:
        uid = _get(settings.HANKO_INTERNAL_URL.rstrip("/") + "/me", token)["id"]
        u = admin_api("GET", f"/users/{uid}")
        user = dict(id=uid, email=primary_email(u), role=role_of(u))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            user = None  # no valid session, or the user was removed
        else:
            raise HTTPException(status_code=503, detail="the login service did not answer")
    except Exception:
        raise HTTPException(status_code=503, detail="the login service did not answer")
    with _lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = (now, user)
    return user


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="sign in first")
    return user


def require_admin(request: Request) -> dict:
    """A FastAPI dependency: the signed-in admin, else 401 (not signed in) or 404 (not an admin)"""
    user = require_user(request)
    if user["role"] != "admin":
        # as if the page did not exist, for anyone who is not an admin
        raise HTTPException(status_code=404, detail="Not Found")
    request.state.user = user
    return user
