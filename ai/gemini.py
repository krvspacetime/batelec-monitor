import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from google import genai
from google.genai import types

from models.models import PowerInterruptionsResponse

from utils.utils import get_cached_data, cache_to_file

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=PowerInterruptionsResponse,
)

images = ["data/img1.jpg", "data/img2.jpg", "data/img3.jpg"]


def upload_content_images(imgs: List[str | Path]):
    images = []
    for img in imgs:
        image = client.files.upload(file=img)
        images.append(image)

    return images


def get_structured_response(
    force: bool = False, images: List[str | Path] = images
) -> PowerInterruptionsResponse:
    if force:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                "These are images containing data about a scheduled power interruption. It is written in a mix of English and Tagalog. Please extract the data and provide it in JSON format according to the response schema. Always use English for the JSON output.",
                *upload_content_images(images),
            ],
            config=config,
        )
        response = response.parsed.model_dump()
        cache_to_file(response, "cache/cached_data.json")
        return PowerInterruptionsResponse(**response)
    else:
        cached_response = get_cached_data("cache/cached_data.json")
        return PowerInterruptionsResponse(**cached_response)
