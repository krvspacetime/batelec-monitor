import os
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

# Load environment variables
load_dotenv()

# Get Supabase URL and key from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLIC_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "SUPABASE_URL and SUPABASE_KEY must be set in environment variables"
    )

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Security scheme for JWT authentication
security = HTTPBearer()


def get_supabase() -> Client:
    """
    Dependency to get Supabase client.

    Returns:
        Client: Supabase client instance
    """
    return supabase


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase_client: Client = Depends(get_supabase),
) -> Dict[str, Any]:
    """
    Verify JWT token and return user information.

    Args:
        credentials: HTTP Authorization credentials containing the JWT token
        supabase_client: Supabase client instance

    Returns:
        Dict[str, Any]: User information

    Raises:
        HTTPException: If token is invalid or user is not authenticated
    """
    try:
        # Get the JWT token from the authorization header
        token = credentials.credentials

        # Check if token already has Bearer prefix and remove it if present
        # This handles cases where users might manually add 'Bearer ' in Swagger UI
        if token.startswith("Bearer "):
            token = token[7:]

        # Ensure token is not empty after processing
        if not token or token.isspace():
            raise ValueError("Empty token provided")

        # Verify the token with Supabase
        user = supabase_client.auth.get_user(token)

        if not user or not user.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_admin_role(
    user: Dict[str, Any] = Depends(get_current_user),
    supabase_client: Client = Depends(get_supabase),
) -> Dict[str, Any]:
    """
    Verify that the authenticated user has admin role.

    Args:
        user: User information from get_current_user dependency
        supabase_client: Supabase client instance

    Returns:
        Dict[str, Any]: User information if user has admin role

    Raises:
        HTTPException: If user does not have admin role
    """
    try:
        # Get user's role from Supabase
        # This assumes you have a 'profiles' table with a 'role' column
        response = (
            supabase_client.table("profiles")
            .select("role")
            .eq("id", user["id"])
            .execute()
        )

        if (
            not response.data
            or len(response.data) == 0
            or response.data[0]["role"] != "admin"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have admin privileges",
            )

        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Failed to verify admin role: {str(e)}",
        )
