import shutil
import uuid

from typing import List
from fastapi import APIRouter, UploadFile, File
from ai.gemini import get_structured_response
from pathlib import Path
from pydantic import BaseModel

router = APIRouter()


class HomeRequest(BaseModel):
    force: bool = False
    fb_post_text: str | None = None
    fb_post_images: List[str | Path] = [
        "data/img1.jpg",
        "data/img2.jpg",
        "data/img3.jpg",
    ]


@router.post("/", tags=["Home"])
async def home(
    request: HomeRequest,
):
    """
    Get the structured response from Gemini.

    Args:
        force: Whether to force re-processing of the images, even if the response is cached. Defaults to False.
        fb_post_text: Text from the Facebook post.
        fb_post_images: List of image files to process.

    Returns:
        The structured response from Gemini.
    """
    structured_response = get_structured_response(
        force=request.force,
        fb_post_text=request.fb_post_text,
        fb_post_images=request.fb_post_images,
    )
    return structured_response


@router.post("/upload-images", tags=["Files"])
async def upload_images(
    images: List[UploadFile] = File(..., description="Multiple files to upload"),
):
    """
    Upload multiple images to be processed by Gemini.

    Args:
        images: List of image files to upload

    Returns:
        List of filenames where the images were saved
    """
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for image in images:
        # Generate a unique filename
        file_extension = Path(image.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename

        # Save the file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        saved_files.append(str(file_path))

    return {"message": "Images uploaded successfully.", "filenames": saved_files}
