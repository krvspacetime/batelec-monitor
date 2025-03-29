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
    system_instruction="You are an expert in data interpretation and extraction. You will receive data from a Facebook post that may or not contain data about a future schedule of a power interruption. The data may contain only images or a mixture of texts from the Facebook post and images. You will figure out if the data provided contains data about a scheduled power interruptio. If not, you will return an empty JSON object otherwise provide the data in JSON format according to the response schema. Always use English for the JSON output.",
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
    force: bool = False,
    fb_post_text: str | None = None,
    fb_post_images: List[str | Path] | None = None,
) -> PowerInterruptionData:
    if fb_post_images is None:
        fb_post_images = ["data/img1.jpg", "data/img2.jpg", "data/img3.jpg"]

    # Validate that all image paths exist
    for img_path in fb_post_images:
        if not Path(img_path).exists():
            raise ValueError(f"Image file not found: {img_path}")

    filename = None
    contents = []
    if fb_post_text:
        contents.append(fb_post_text)
    if fb_post_images:
        contents.extend(upload_content_images(fb_post_images))
    if force:
        response = client.models.generate_content(
            model="gemini-2.5-pro-exp-03-25",
            contents=contents,
            config=config,
        )
        response = response.parsed.model_dump()
        filename = f"cached_data_{response['date']}_{response['start_time']}_{response['end_time']}.json"
        cache_to_file(response, filename)
        return PowerInterruptionData(**response)
    else:
        cached_response = get_cached_data()
        return PowerInterruptionData(**cached_response)
