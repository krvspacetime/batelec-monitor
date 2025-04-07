import traceback
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from supabase import Client

from db.supabase import get_current_user, get_supabase

# Create a router for authentication endpoints
router = APIRouter(prefix="/auth", tags=["Authentication"])


class UserRegisterRequest(BaseModel):
    """Request model for user registration"""

    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password", min_length=6)
    full_name: Optional[str] = Field(None, description="User's full name")


class UserLoginRequest(BaseModel):
    """Request model for user login"""

    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")


class PasswordResetRequest(BaseModel):
    """Request model for password reset request"""

    email: EmailStr = Field(..., description="User's email address")


class PasswordUpdateRequest(BaseModel):
    """Request model for password update"""

    password: str = Field(..., description="New password", min_length=6)


class AuthResponse(BaseModel):
    """Response model for authentication operations"""

    message: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register_user(
    request: UserRegisterRequest, supabase: Client = Depends(get_supabase)
):
    """Register a new user"""
    try:
        # Register user with Supabase Auth
        response = supabase.auth.sign_up(
            {
                "email": request.email,
                "password": request.password,
                "options": {"data": {"full_name": request.full_name or ""}},
            }
        )

        return AuthResponse(
            message="User registered successfully. Please check your email for verification.",
            user=response.user.model_dump() if response.user else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during registration: {str(e)}",
        )


@router.post("/login", response_model=AuthResponse)
async def login_user(
    request: UserLoginRequest, supabase: Client = Depends(get_supabase)
):
    """Login a user with email and password"""
    try:
        # Authenticate user with Supabase Auth
        response = supabase.auth.sign_in_with_password(
            {"email": request.email, "password": request.password}
        )
        return AuthResponse(
            message="Login successful",
            access_token=response.session.access_token if response.session else None,
            refresh_token=response.session.refresh_token if response.session else None,
            user=response.user.model_dump() if response.user else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during login: {str(e)}",
        )


@router.post("/logout", response_model=AuthResponse)
async def logout_user(
    supabase: Client = Depends(get_supabase),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Logout the current user"""
    try:
        # Sign out the user
        supabase.auth.sign_out()

        return AuthResponse(message="Logout successful")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during logout: {str(e)}",
        )


@router.post("/password-reset/request", response_model=AuthResponse)
async def request_password_reset(
    request: PasswordResetRequest, supabase: Client = Depends(get_supabase)
):
    """Request a password reset email"""
    try:
        # Send password reset email
        response = supabase.auth.reset_password_email(request.email)

        if response.error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password reset request failed: {response.error.message}",
            )

        return AuthResponse(
            message="Password reset email sent. Please check your email."
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during password reset request: {str(e)}",
        )


@router.post("/password-reset/update", response_model=AuthResponse)
async def update_password(
    request: PasswordUpdateRequest,
    supabase: Client = Depends(get_supabase),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Update user password (requires authentication)"""
    try:
        # Update user password
        response = supabase.auth.update_user({"password": request.password})

        if response.error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password update failed: {response.error.message}",
            )

        return AuthResponse(message="Password updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during password update: {str(e)}",
        )


@router.get("/me")
async def get_current_user_info(
    user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get current user information"""
    try:
        return user
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while retrieving user information: {str(e)}",
        )
