import logging
import os
import time
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from starlette import status
from supabase import Client

# Import the improved scraper implementation
from scraper.scraper import scrape_facebook_page
from scraper.scrape_utils import check_rate_limit
from db.supabase import get_supabase
from models.scraper import (
    ScrapeRequest,
    ScrapeResponse,
    ScrapeStatusResponse,
    PostData,
    PostsResponse,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper.log"),
    ],
)

logger = logging.getLogger(__name__)

# Create router with prefix
router = APIRouter(prefix="/scrape", tags=["Scraper"])

# Store active scraping tasks to prevent duplicates
active_scraping_tasks = {}


def scrape_task(supabase: Client, task_id: str, scrape_params: ScrapeRequest):
    """Background task to handle Facebook page scraping"""
    try:
        # Update task status to processing before starting the actual work
        active_scraping_tasks[task_id].update(
            {
                "status": "processing",
                "message": "Scraper is processing the page",
                "last_updated": datetime.now().isoformat(),
            }
        )

        # Create output directory if specified
        output_dir = scrape_params.output_dir
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_dir = "data"
            os.makedirs(output_dir, exist_ok=True)

        # Generate filenames with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(output_dir, f"scraper_log_{timestamp}.log")

        # Set HTML and JSON file paths based on save preferences
        # HTML file is set to None if save_html is False
        html_file = None
        if scrape_params.save_html:
            html_file = os.path.join(output_dir, f"facebook_page_{timestamp}.html")

        # JSON file path
        json_file = None
        if scrape_params.save_json:
            json_file = os.path.join(output_dir, f"facebook_data_{timestamp}.json")

        # Call the improved scraper function with all available parameters
        # Update task status to indicate scraping has started
        active_scraping_tasks[task_id].update(
            {
                "status": "scraping",
                "message": "Scraper is actively scraping the page",
                "last_updated": datetime.now().isoformat(),
            }
        )

        scrape_result = scrape_facebook_page(
            url=scrape_params.url,
            supabase=supabase,
            sleep_time=scrape_params.sleep_time,
            max_scrolls=scrape_params.max_scrolls,
            headless=scrape_params.headless,
            log_file=log_file,
            proxy=scrape_params.proxy,
        )

        # Update task status based on scraper result
        if scrape_result["success"]:
            active_scraping_tasks[task_id] = {
                "status": "completed",
                "message": "Scraping completed successfully",
                "result": {
                    "html_file": scrape_result.get("html_file", html_file),
                    "json_file": scrape_result.get("json_file", json_file),
                    "log_file": log_file,
                    "timestamp": timestamp,
                    "stats": scrape_result.get("stats", {}),
                    "post_count": len(scrape_result.get("posts", [])),
                },
                "error": None,
                "posts": scrape_result.get(
                    "posts", []
                ),  # Store posts data for direct API access
                "last_updated": datetime.now().isoformat(),
            }
            logger.info(
                f"Task {task_id} completed successfully with {len(scrape_result.get('posts', []))} posts"
            )
        else:
            active_scraping_tasks[task_id] = {
                "status": "failed",
                "message": "Scraping failed",
                "result": {
                    "log_file": log_file,
                    "timestamp": timestamp,
                    "stats": scrape_result.get("stats", {}),
                },
                "error": scrape_result.get("error", "Unknown error"),
                "posts": [],  # Empty posts array for failed tasks
                "last_updated": datetime.now().isoformat(),
            }
            logger.error(f"Task {task_id} failed: {scrape_result.get('error')}")

    except Exception as e:
        logger.error(f"Error in scraping task {task_id}: {str(e)}")
        active_scraping_tasks[task_id] = {
            "status": "failed",
            "message": "Scraping failed",
            "result": None,
            "error": str(e),
            "posts": [],  # Ensure posts field exists even on error
            "last_updated": datetime.now().isoformat(),
        }
    finally:
        # Keep task result for a limited time (could implement cleanup later)
        pass


@router.post(
    "/facebook", response_model=ScrapeResponse, status_code=status.HTTP_202_ACCEPTED
)
def scrape_facebook(
    request: Request,
    scrape_request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    supabase: Client = Depends(get_supabase),
):
    """Endpoint to initiate Facebook page scraping"""
    # Check rate limiting
    if not check_rate_limit(request):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
        )

    # Validate URL format
    if (
        not scrape_request.url
        or scrape_request.url == "string"
        or not scrape_request.url.startswith("http")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL provided. URL must be a valid HTTP or HTTPS URL.",
        )

    # Generate a unique task ID
    task_id = f"scrape_{int(time.time())}_{hash(scrape_request.url) % 10000}"

    # Check if there's already an active task for this URL
    for existing_id, task_info in active_scraping_tasks.items():
        if (
            task_info.get("url") == scrape_request.url
            and task_info.get("status") == "in_progress"
        ):
            return ScrapeResponse(
                task_id=existing_id,
                status="in_progress",
                message="A scraping task for this URL is already in progress",
                timestamp=datetime.now().isoformat(),
            )

    # Store task information
    current_time = datetime.now().isoformat()
    active_scraping_tasks[task_id] = {
        "status": "in_progress",
        "message": "Scraping started",
        "url": scrape_request.url,
        "timestamp": current_time,
        "last_updated": current_time,
        "posts": [],  # Initialize empty posts array
    }

    # Add task to background tasks
    background_tasks.add_task(scrape_task, supabase, task_id, scrape_request)

    logger.info(f"Started scraping task {task_id} for URL: {scrape_request.url}")

    return ScrapeResponse(
        task_id=task_id,
        status="in_progress",
        message="Scraping task started",
        timestamp=datetime.now().isoformat(),
    )


@router.get("/status/{task_id}", response_model=ScrapeStatusResponse)
def get_scrape_status(task_id: str):
    """Get the status of a scraping task

    This endpoint returns immediately with the current status of the task,
    rather than waiting for the task to complete.
    """
    if task_id not in active_scraping_tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    task_info = active_scraping_tasks[task_id]

    # Return the current status immediately
    return ScrapeStatusResponse(
        task_id=task_id,
        status=task_info.get("status", "unknown"),
        message=task_info.get("message", ""),
        result=task_info.get("result"),
        error=task_info.get("error"),
        last_updated=task_info.get("last_updated", datetime.now().isoformat()),
    )


@router.get("/posts/{task_id}", response_model=PostsResponse)
async def get_posts(task_id: str):
    """Get the posts data from a completed scraping task"""
    if task_id not in active_scraping_tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    task_info = active_scraping_tasks[task_id]

    if task_info.get("status") != "completed":
        return PostsResponse(
            task_id=task_id,
            status=task_info.get("status", "unknown"),
            posts=[],
            stats=task_info.get("result", {}).get("stats")
            if task_info.get("result")
            else None,
        )

    # Convert posts to Pydantic models
    posts = [PostData(**post) for post in task_info.get("posts", [])]

    return PostsResponse(
        task_id=task_id,
        status="completed",
        posts=posts,
        stats=task_info.get("result", {}).get("stats")
        if task_info.get("result")
        else None,
    )


@router.get("/tasks", response_model=Dict[str, Dict])
async def list_scrape_tasks():
    """List all scraping tasks and their statuses"""
    # Return a simplified view of tasks without the full posts data to avoid large responses
    simplified_tasks = {}
    for task_id, task_info in active_scraping_tasks.items():
        task_copy = task_info.copy()
        if "posts" in task_copy:
            # Just include the count instead of full post data
            task_copy["post_count"] = len(task_copy["posts"])
            del task_copy["posts"]
        simplified_tasks[task_id] = task_copy

    return simplified_tasks


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str):
    """Delete a task and its associated data"""
    if task_id not in active_scraping_tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # Check if task is still in progress
    if active_scraping_tasks[task_id].get("status") == "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a task that is still in progress",
        )

    # Remove the task
    del active_scraping_tasks[task_id]

    return None
