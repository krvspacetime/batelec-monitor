import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from google import genai
from google.genai import types

from models.models import PowerInterruptionData

from utils.utils import get_cached_data, cache_to_file

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=PowerInterruptionData,
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
) -> PowerInterruptionData:
    cached_exists = os.path.exists("cache/cached_data.json")
    filename = None
    if force or not cached_exists:
        response = client.models.generate_content(
            model="gemini-2.5-pro-exp-03-25",
            contents=[
                "These are texts (if provided) and images containing data about a scheduled power interruption from a Facebook post. It is written in a mix of English and Tagalog. Please extract the data and provide it in JSON format according to the response schema. Make sure to figure out from the images whether this is an update or a new announcement and include this in the response schema. Always use English for the JSON output.",
                *upload_content_images(images),
            ],
            config=config,
        )
        response = response.parsed.model_dump()
        filename = f"cached_data_{response['date']}_{response['start_time']}_{response['end_time']}.json"
        cache_to_file(response, filename)
        return PowerInterruptionData(**response)
    else:
        cached_response = get_cached_data()
        return PowerInterruptionData(**cached_response)
