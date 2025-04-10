from pydantic import BaseModel
from typing import Dict, List


class ResultFormat(BaseModel):
    text: str
    img_links: List[str]


class PostComparisonResult(BaseModel):
    are_same_data: bool
    message: str
    new_posts: ResultFormat | None = None
