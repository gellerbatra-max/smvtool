"""api.py -- thin, client-agnostic HTTP wrapper for the demo seed.

`ApiSession` never mutates the underlying client's own headers; every
request passes the calling `Actor`'s Authorization header explicitly, so
one client (an `httpx.Client` against a real bound port, or a
`fastapi.testclient.TestClient` in tests) can safely serve multiple
logged-in users within a single seed run. That's what makes multi-user
attribution (created_by_id / computed_by_id / change_log.user_id) fall
out of the seed for free, without any direct database access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class SeedApiError(RuntimeError):
    """Raised for any non-success HTTP response. Carries enough to build a
    SeedReport.failed entry without the caller re-parsing anything."""

    def __init__(self, context: str, status: int, detail: str):
        super().__init__(f"{context}: {status} {detail[:300]}")
        self.context = context
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class Actor:
    """One logged-in identity the seed can act as."""
    username: str
    user_id: str
    headers: dict[str, str]


class ApiSession:
    """Wraps any client exposing httpx-style .get/.post/.put/.patch/.delete
    methods (both httpx.Client and starlette's TestClient qualify)."""

    def __init__(self, client: Any):
        self._client = client

    def login(self, username: str, password: str) -> Actor:
        # /auth/login takes OAuth2PasswordRequestForm -- form-encoded, not JSON.
        r = self._client.post("/auth/login", data={"username": username, "password": password})
        if r.status_code != 200:
            raise SeedApiError(f"login as {username!r}", r.status_code, r.text)
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = self._client.get("/auth/me", headers=headers)
        if me.status_code != 200:
            raise SeedApiError(f"GET /auth/me as {username!r}", me.status_code, me.text)
        return Actor(username=username, user_id=me.json()["id"], headers=headers)

    def get(self, path: str, actor: Actor, *, ok: Iterable[int] = (200,), **kw) -> Any:
        r = self._client.get(path, headers=actor.headers, **kw)
        return self._unwrap(r, f"GET {path}", ok)

    def post(self, path: str, actor: Actor, *, ok: Iterable[int] = (200, 201), **kw) -> Any:
        r = self._client.post(path, headers=actor.headers, **kw)
        return self._unwrap(r, f"POST {path}", ok)

    def put(self, path: str, actor: Actor, *, ok: Iterable[int] = (200,), **kw) -> Any:
        r = self._client.put(path, headers=actor.headers, **kw)
        return self._unwrap(r, f"PUT {path}", ok)

    def patch(self, path: str, actor: Actor, *, ok: Iterable[int] = (200,), **kw) -> Any:
        r = self._client.patch(path, headers=actor.headers, **kw)
        return self._unwrap(r, f"PATCH {path}", ok)

    def delete(self, path: str, actor: Actor, *, ok: Iterable[int] = (204,), **kw) -> Any:
        r = self._client.delete(path, headers=actor.headers, **kw)
        return self._unwrap(r, f"DELETE {path}", ok)

    @staticmethod
    def _unwrap(r, context: str, ok: Iterable[int]) -> Any:
        if r.status_code not in ok:
            raise SeedApiError(context, r.status_code, r.text)
        # A 204 (delete) has no body. Returning True rather than None for
        # that case matters: callers use `_try(...) is None` to mean
        # "failed" -- if a *successful* empty-body call also returned None,
        # success and failure would be indistinguishable.
        return r.json() if r.content else True
