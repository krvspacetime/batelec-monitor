import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from google import genai
from google.genai import types

from models.models import PowerInterruptionData
from ai.utils import upload_images_from_urls


load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
config = types.GenerateContentConfig(
    system_instruction="You are an expert in data interpretation and extraction. The data might be written in a mixture of English and Tagalog but make absolutely sure to translate everything to English. You will receive data from a Facebook post that may or not contain data about a future schedule of a power interruption. The data may contain only images or a mixture of texts from the Facebook post and images. You will figure out if the data provided contains data about a scheduled power interruptio. If not, you will return an empty JSON object otherwise provide the data in JSON format according to the response schema. Make sure to parse dates and time that can easily be used in Python",
    response_mime_type="application/json",
    response_schema=PowerInterruptionData,
)


def get_structured_response(
    fb_post_text: str | None = None,
    fb_post_images: List[str | Path] | None = None,
) -> PowerInterruptionData:
    contents = []
    if fb_post_text:
        contents.append(fb_post_text)
    if fb_post_images:
        contents.extend(upload_images_from_urls(client, fb_post_images))
    response = client.models.generate_content(
        # model="gemini-2.5-pro-exp-03-25",
        model="gemini-2.0-flash",
        contents=contents,
        config=config,
    )
    response = response.parsed.model_dump()
    return PowerInterruptionData(**response)
