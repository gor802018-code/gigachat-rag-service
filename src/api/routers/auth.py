"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_auth_service
from src.api.schemas import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from src.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidEmailError,
    WeakPasswordError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: UserRegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        user = await service.register(payload.email, payload.password)
    except (InvalidEmailError, WeakPasswordError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return UserResponse.from_domain(user)


@router.post("/login", response_model=TokenResponse, summary="Get a JWT access token")
async def login(
    payload: UserLoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        result = await service.login(payload.email, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return TokenResponse.from_auth_result(result)
