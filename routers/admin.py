import logging  # Add this import

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import (  # Import PostgrestAPIResponse for type hints
    Client,
)

from ai.gemini import get_structured_response
from ai.utils import extract_post_data, find_new_posts

from db.supabase import (
    get_current_user,
    get_supabase,
    list_files_in_folder,
    read_file_from_bucket,
)
from scraper.scraper import scrape_facebook_page
from utils.admin_utils import process_and_create_interruption_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class AdminRequest(BaseModel):
    """
    Request model for the admin endpoint.

    Attributes:
        fb_post_text: Text content of a Facebook post
        fb_post_images: List of image paths from a Facebook post
    """

    fb_post_text: str | None = None
    fb_post_images: List[str | Path] = []


# --- Refactored FastAPI Route ---
@router.post("/")
async def admin(
    user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Receives Facebook post text and images, processes them via AI,
    checks relevance, and IF relevant, creates a new power interruption record
    and associated data in the database. Assumes the post data provided
    corresponds to a *new* post identified by a prior process.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: User not authenticated.",
        )
    try:
        # Get latest `extracted_posts.json` from bucket
        logger.info("Fetching latest posts from bucket...")
        posts_data_folders = list_files_in_folder(
            supabase, "scraper-data", None, None, False
        )
        if posts_data_folders == []:
            logger.error("Directory is empty.")
            logger.error("Directory is empty.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Directory is empty.",
            )
        latest_folder = posts_data_folders[0].get("name", None)
        if not latest_folder:
            logger.error("No valid folder name found in bucket.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No valid folder name found in bucket.",
            )
        old_posts_json = read_file_from_bucket(
            supabase, f"{latest_folder}/extracted_posts.json", "scraper-data"
        )

        # Run scrape job
        latest_posts_json = scrape_facebook_page(
            url="https://www.facebook.com/Batangas1ElectricCooperativeInc",
            supabase=supabase,
        )

        formatted_old_posts = extract_post_data(old_posts_json)
        formatted_latest_posts = extract_post_data(latest_posts_json)

        new_posts = find_new_posts(formatted_old_posts, formatted_latest_posts)

        if not new_posts:
            logger.warning("No new posts found. Skipping AI processing.")
            return {
                "message": "No new posts found",
                "processed_data_preview": formatted_latest_posts,
            }

        # --- 1. Get structured response from AI model ---
        logger.info("Requesting structured response from AI model...")

        # Make sure get_structured_response returns a Pydantic model or similar
        # that has a .model_dump() method or can be easily converted to dict.
        valid_posts = []
        for post in new_posts:
            structured_response_model = get_structured_response(
                fb_post_text=post["text"],
                fb_post_images=post["img_links"],
            )
            # Convert Pydantic model (or similar) to dictionary
            data_dict = structured_response_model.model_dump()  # Assumes Pydantic V2+
            logger.info("Received structured response from AI.")
            logger.debug(f"AI Response Data Preview (dict): {data_dict}")

            # --- 2. Check relevance ---
            if not data_dict.get("is_power_interruption_related", False):
                logger.warning(
                    "AI determined post is NOT power interruption related. Skipping DB operations."
                )
                continue
            valid_posts.append(data_dict)

        if not valid_posts:
            logger.warning("No valid posts found. Skipping DB operations.")
            return {
                "message": "No valid posts found",
                "processed_data_preview": new_posts,
            }

        # --- 3. Process and Create Record (Call extracted function) ---
        # NO explicit existence check (Step 4) is performed here.
        # We directly call the function to process and insert.
        new_record_id = await process_and_create_interruption_record(
            structured_data=data_dict,
            supabase=supabase,
            logger=logger,
        )

        # --- 4. Success Response ---
        logger.info(
            f"Successfully created and linked new power interruption record ID: {new_record_id}"
        )
        return {
            "message": "Success: New power interruption record created",
            "record_id": new_record_id,
            "processed_data_preview": data_dict,
        }

    except HTTPException as http_exc:
        # Logged already where raised, re-raise
        raise http_exc
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in the admin endpoint: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # Use 500 for unexpected
            detail=f"An unexpected server error occurred: {str(e)}",
        )


# --- Helper Function for Get-or-Create Pattern ---
async def get_or_create_related_item(
    supabase: Client,
    logger: logging.Logger,
    table_name: str,
    item_data: Dict[str, Any],
    match_columns: List[str],
) -> int | None:
    """
    Checks if an item exists based on match_columns, inserts if not, returns the ID.
    """
    try:
        # Build query dynamically based on match_columns
        query = supabase.table(table_name).select("id")
        log_match_str = []
        for col in match_columns:
            value = item_data.get(col)
            if value is None:  # Cannot match on None usually
                logger.warning(
                    f"Missing value for match column '{col}' in table '{table_name}'. Cannot get/create item: {item_data}"
                )
                return None
            query = query.eq(col, value)
            log_match_str.append(f"{col}='{value}'")
        match_str = " AND ".join(log_match_str)

        logger.debug(
            f"Checking table '{table_name}' for existing item where {match_str}"
        )
        check_response = query.execute()

        if check_response.data and len(check_response.data) > 0:
            item_id = check_response.data[0]["id"]
            logger.debug(
                f"Found existing item in '{table_name}' with ID: {item_id} for {match_str}"
            )
            return item_id
        else:
            logger.debug(
                f"Item not found in '{table_name}' where {match_str}. Inserting new item."
            )
            logger.debug(f"Data for insert: {item_data}")
            insert_response = supabase.table(table_name).insert(item_data).execute()
            if insert_response.data and len(insert_response.data) > 0:
                new_item_id = insert_response.data[0]["id"]
                logger.debug(
                    f"Successfully inserted item into '{table_name}'. New ID: {new_item_id}"
                )
                return new_item_id
            else:
                logger.error(
                    f"Failed to insert item into '{table_name}'. Data: {item_data}. Response: {insert_response.data}, Status: {insert_response.status_code}"
                )
                return None
    except Exception as db_exc:
        logger.error(
            f"Database error during get_or_create for table '{table_name}', data {item_data}: {db_exc}",
            exc_info=True,
        )
        return None  # Indicate failure


@router.get("/files")
async def get_files_from_bucket(
    supabase: Client = Depends(get_supabase),
    bucket_name: str = "scraper-data",
    folder_path: str | None = None,
    target_most_recent: bool = False,
    files_only: bool = False,
):
    try:
        response = list_files_in_folder(
            supabase, bucket_name, folder_path, files_only, target_most_recent
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/read_file")
async def read_json_from_bucket(
    file_path: str,
    supabase: Client = Depends(get_supabase),
    bucket_name: str = "scraper-data",
):
    try:
        response = read_file_from_bucket(supabase, file_path, bucket_name)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare")
async def compare(supabase: Client = Depends(get_supabase)):
    old = read_file_from_bucket(
        supabase, "20250410_125952_610425/extracted_posts.json", "scraper-data"
    )
    new = read_file_from_bucket(
        supabase, "20250410_154212_454437/extracted_posts.json", "scraper-data"
    )
    new_posts = find_new_posts(old, new)
    return new_posts
