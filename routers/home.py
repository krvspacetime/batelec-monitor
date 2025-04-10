import shutil
import uuid

from typing import List
from fastapi import APIRouter, UploadFile, File
from ai.gemini import get_structured_response
from pathlib import Path
from pydantic import BaseModel

router = APIRouter()


class HomeRequest(BaseModel):
    fb_post_text: str | None = None
    fb_post_images: List[str | Path] | None = None


image_links = [
    "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/489013393_1071257381695546_5153001472698797066_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=0CkCykRHaGUQ7kNvwGz5AUe&_nc_oc=Adl-DVc8voYjQj864Lx8lnNkniDVS1bfgZc2_r48u1HoMpgyLQIWMJi2kyk5Fnx2sPY&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfERiuleshZEjWeyTfIrDGFAW74iJlPK2uqK1iVwOH75mw&oe=67FA26C4",
    "https://scontent.fmnl3-3.fna.fbcdn.net/v/t39.30808-6/489145161_1071257375028880_4532715069200241563_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=111&ccb=1-7&_nc_sid=127cfc&_nc_ohc=O8XXqPUswaQQ7kNvwFrKeuK&_nc_oc=Adk-sUaTe1cU4tqfnWLNzo1QLSW9D2dg2Wh4ElDCk4CeW9pgzlImV9cYM2zoBSVoVTQ&_nc_zt=23&_nc_ht=scontent.fmnl3-3.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfEeGfR9h05H_2UobwhNoQ3EPN8ggKe699z-MVn9O-Fj9Q&oe=67FA1A88",
    "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",  # Example with clearer filename
    # Add more image URLs here if needed
]


@router.post("/", tags=["Home"])
async def home(
    request: HomeRequest,
):
    """Get the structured response from Gemini.

    Args:
        fb_post_text: Text from the Facebook post.
        fb_post_images: List of image files to process.

    Returns:
        The structured response from Gemini.
    """
    structured_response = get_structured_response(
        fb_post_text=request.fb_post_text,
        fb_post_images=request.fb_post_images
        if request.fb_post_images
        else image_links,
    )
    return structured_response


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
