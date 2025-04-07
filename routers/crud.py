import traceback
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from supabase import Client

from db.supabase import get_supabase, verify_admin_role

# Create a protected router with admin authentication
router = APIRouter(prefix="/crud", tags=["CRUD"])


class GenericRequest(BaseModel):
    """Generic request model for CRUD operations"""

    data: Dict[str, Any] = Field(..., description="Data to be processed")


class GenericResponse(BaseModel):
    """Generic response model for CRUD operations"""

    message: str
    data: Optional[Any] = None


@router.get("/{table_name}", response_model=GenericResponse)
async def get_table(
    supabase: Client = Depends(get_supabase),
):
    """Get a specific table's data"""
    try:
        response = supabase.table("power_interruption_data").select("*").execute()
        return response
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {str(e)}",
        )


@router.post(
    "/{table_name}", response_model=GenericResponse, status_code=status.HTTP_201_CREATED
)
async def create_record(
    request: GenericRequest,
    table_name: str = Path(..., description="Name of the table to insert into"),
    user: Dict[str, Any] = Depends(verify_admin_role),
    supabase: Client = Depends(get_supabase),
):
    """Create a new record in a specific table"""
    try:
        response = supabase.table(table_name).insert(request.data).execute()

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create record in {table_name}",
            )

        return GenericResponse(
            message=f"Successfully created record in {table_name}",
            data=response.data[0],
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {str(e)}",
        )
