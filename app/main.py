from __future__ import annotations

import ssl
from functools import lru_cache
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import jwt
from jose.exceptions import JWTError
from markdown_it import MarkdownIt
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    keycloak_base_url: str = Field(
        default="https://keycloak.local.test",
        description="Base URL for Keycloak, for example https://keycloak.example.com",
    )
    keycloak_realm: str = Field(default="demo")
    keycloak_client_id: str = Field(default="fastapi-client")
    keycloak_audience: str | None = Field(
        default=None,
        description="Expected access-token audience. Defaults to keycloak_client_id when not set.",
    )
    keycloak_verify_ssl: bool = Field(default=True)
    keycloak_required_role: str = Field(default="red")


@lru_cache
def get_settings() -> Settings:
    return Settings()


class CurrentUser(BaseModel):
    subject: str
    username: str | None = None
    email: str | None = None
    roles: set[str]
    claims: dict[str, Any]


security = HTTPBearer(auto_error=False)
app = FastAPI(title="Markdown Preview App")

# Templates + static
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Server-side markdown renderer (optional endpoint)
md = MarkdownIt("commonmark")


def issuer_url(settings: Settings) -> str:
    return f"{settings.keycloak_base_url.rstrip('/')}/realms/{settings.keycloak_realm}"


def jwks_url(settings: Settings) -> str:
    return f"{issuer_url(settings)}/protocol/openid-connect/certs"


@lru_cache
def get_keycloak_jwks() -> dict[str, Any]:
    settings = get_settings()
    response = httpx.get(jwks_url(settings), verify=settings.keycloak_verify_ssl, timeout=10)
    response.raise_for_status()
    return response.json()


def extract_roles(claims: dict[str, Any], client_id: str) -> set[str]:
    realm_roles = set(claims.get("realm_access", {}).get("roles", []))
    client_roles = set(
        claims.get("resource_access", {})
        .get(client_id, {})
        .get("roles", [])
    )
    return realm_roles | client_roles


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    expected_audience = settings.keycloak_audience or settings.keycloak_client_id

    try:
        return jwt.decode(
            token,
            get_keycloak_jwks(),
            algorithms=["RS256"],
            issuer=issuer_url(settings),
            audience=expected_audience,
            options={"verify_aud": bool(expected_audience)},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    print("HELLO")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_token(credentials.credentials, settings)
    roles = extract_roles(claims, settings.keycloak_client_id)

    return CurrentUser(
        subject=claims.get("sub", ""),
        username=claims.get("preferred_username"),
        email=claims.get("email"),
        roles=roles,
        claims=claims,
    )


def require_role(required_role: str):
    async def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if required_role not in current_user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required role: {required_role}",
            )
        return current_user

    return dependency


async def require_configured_role(
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if settings.keycloak_required_role not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required role: {settings.keycloak_required_role}",
        )
    return current_user


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    # We render the preview primarily in the browser for instant feedback.
    # This page just loads the UI.
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "subject": current_user.subject,
        "username": current_user.username,
        "email": current_user.email,
        "roles": sorted(current_user.roles),
    }


@app.post("/render", response_class=JSONResponse)
async def render_markdown(
    markdown_text: str = Form(...),
    # current_user: CurrentUser = Depends(require_configured_role),
) -> JSONResponse:
    """
    Server-side render endpoint protected by Keycloak OIDC.
    The caller must provide a valid Bearer token with the configured role.
    """
    html = md.render(markdown_text)
    return JSONResponse(
        {
            "html": html,
            "rendered_by": current_user.username or current_user.subject,
        }
    )


@app.post("/render/public", response_class=JSONResponse)
async def render_markdown_public(markdown_text: str = Form(...)) -> JSONResponse:
    """
    Optional unprotected render endpoint for local testing.
    Remove this endpoint if all rendering should require authentication.
    """
    html = md.render(markdown_text)
    return JSONResponse({"html": html})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        # ssl_certfile="./localhost+2.pem",
        # ssl_keyfile="./localhost+2-key.pem",
        # ssl_ca_certs="/Users/carlos/Library/Application Support/mkcert/rootCA.pem",
        # ssl_cert_reqs=ssl.CERT_REQUIRED,  # mTLS
    )