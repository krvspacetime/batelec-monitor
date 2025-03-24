from fastapi import APIRouter
from ai.gemini import get_structured_response

router = APIRouter()


@router.get("/", tags=["Home"])
async def home(force: bool = False):
    structured_response = get_structured_response(force=force)
    return structured_response
