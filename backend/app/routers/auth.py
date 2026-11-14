from fastapi import APIRouter, Depends, Request, Response, status

from app.core.errors import Unauthorized
from app.core.security import TokenType
from app.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    AuthDep,
    CurrentUserDep,
    SettingsDep,
    client_info,
    verify_origin,
)
from app.schemas.auth import LoginRequest, MeResponse, SignupRequest, TenantOut, UserOut
from app.services.auth import IssuedSession

router = APIRouter(prefix="/api/v1", tags=["auth"], dependencies=[Depends(verify_origin)])

REFRESH_PATH = "/api/v1/auth"


def _set_session_cookies(response: Response, issued: IssuedSession, settings: SettingsDep) -> None:
    secure = settings.secure_cookies
    response.set_cookie(
        ACCESS_COOKIE,
        issued.access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    # Refresh token is only ever sent to the auth endpoints.
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=REFRESH_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def _clear_session_cookies(response: Response, settings: SettingsDep) -> None:
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, REFRESH_PATH)):
        response.delete_cookie(
            name, path=path, httponly=True, secure=settings.secure_cookies, samesite="lax"
        )


def _me(issued: IssuedSession) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(issued.user), tenant=TenantOut.model_validate(issued.tenant)
    )


@router.post("/auth/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
) -> MeResponse:
    issued = await auth.signup(body, client_info(request))
    _set_session_cookies(response, issued, settings)
    return _me(issued)


@router.post("/auth/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
) -> MeResponse:
    issued = await auth.login(body, client_info(request))
    _set_session_cookies(response, issued, settings)
    return _me(issued)


@router.post("/auth/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def refresh(
    request: Request, response: Response, auth: AuthDep, settings: SettingsDep
) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise Unauthorized("Session expired")
    try:
        issued = await auth.refresh(token)
    except Unauthorized:
        _clear_session_cookies(response, settings)
        raise
    _set_session_cookies(response, issued, settings)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, auth: AuthDep, settings: SettingsDep
) -> None:
    if token := request.cookies.get(REFRESH_COOKIE):
        await auth.logout(token, TokenType.REFRESH)
    elif token := request.cookies.get(ACCESS_COOKIE):
        await auth.logout(token, TokenType.ACCESS)
    _clear_session_cookies(response, settings)


@router.get("/me")
async def me(current: CurrentUserDep) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(current.user),
        tenant=TenantOut.model_validate(current.tenant),
    )
