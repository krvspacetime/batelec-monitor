from pydantic import BaseModel, Field
from typing import Optional, Dict, List


class ScrapeRequest(BaseModel):
    url: str = Field(
        "https://www.facebook.com/Batangas1ElectricCooperativeInc",
        description="Facebook page URL to scrape",
    )
    max_scrolls: int = Field(15, description="Maximum number of page scrolls")
    sleep_time: int = Field(5, description="Sleep time between scrolls in seconds")
    output_dir: Optional[str] = Field(
        None, description="Directory to save output files (optional)"
    )
    headless: bool = Field(True, description="Run browser in headless mode")
    proxy: Optional[str] = Field(
        None, description="Proxy server to use (format: 'http://user:pass@host:port')"
    )
    save_html: bool = Field(False, description="Whether to save HTML output")
    save_json: bool = Field(True, description="Whether to save JSON output")


class ScrapeResponse(BaseModel):
    task_id: str
    status: str
    message: str
    timestamp: str


class ScrapeStatusResponse(BaseModel):
    task_id: str
    status: str
    message: str
    result: Optional[Dict] = None
    error: Optional[str] = None
    last_updated: Optional[str] = None


class PostData(BaseModel):
    text: str = ""
    img_links: List[str] = []
    timestamp: Optional[str] = None


class PostsResponse(BaseModel):
    task_id: str
    status: str
    posts: List[PostData] = []
    stats: Optional[Dict] = None
