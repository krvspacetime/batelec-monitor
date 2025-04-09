import datetime
import json
import logging
import mimetypes
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue import UserResponse
from pydantic import BaseModel, Field
from supabase import Client, PostgrestAPIResponse, create_client

# Load environment variables
load_dotenv()

# --- Logger Setup ---
log_filename = "supabase.log"
# Configure to log to both file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(),  # Log to console
    ],
)
logger = logging.getLogger(__name__)

# Get Supabase URL and key from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLIC_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "SUPABASE_URL and SUPABASE_KEY must be set in environment variables"
    )

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Security scheme for JWT authentication
security = HTTPBearer()


def get_supabase() -> Client:
    """
    Dependency to get Supabase client.

    Returns:
        Client: Supabase client instance
    """
    return supabase


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase_client: Client = Depends(get_supabase),
) -> Dict[str, Any]:
    """
    Verify JWT token and return user information.

    Args:
        credentials: HTTP Authorization credentials containing the JWT token
        supabase_client: Supabase client instance

    Returns:
        Dict[str, Any]: User information

    Raises:
        HTTPException: If token is invalid or user is not authenticated
    """
    try:
        # Get the JWT token from the authorization header
        token = credentials.credentials

        # Check if token already has Bearer prefix and remove it if present
        # This handles cases where users might manually add 'Bearer ' in Swagger UI
        if token.startswith("Bearer "):
            token = token[7:]

        # Ensure token is not empty after processing
        if not token or token.isspace():
            raise ValueError("Empty token provided")

        # Verify the token with Supabase
        user = supabase_client.auth.get_user(token)

        if not user or not user.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_admin_role(
    supabase: Client = Depends(get_supabase),
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:  # Return the user data if verification passes
    """
    FastAPI dependency that verifies if the current authenticated user
    has the 'admin' role in the public.profiles table. (SYNC VERSION)
    """
    # Extract user ID
    # Corrected based on your note: current_user.user.id
    user_id = current_user.user.id if current_user and current_user.user else None

    if not user_id:
        logger.warning("Could not extract user ID from UserResponse object.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate user credentials.",
        )

    logger.debug(f"Verifying admin role for user ID: {user_id}")

    is_admin = False
    try:
        # Query the profiles table for the user's role
        # REMOVE await keyword
        response: PostgrestAPIResponse = (
            supabase.table("profiles").select("role").eq("user_id", user_id).execute()
        )  # No await here

        # Check if profile exists and role is 'admin'
        # response.data structure might differ slightly between sync/async, verify if needed
        profile_data = (
            response.data
        )  # maybe_single() often puts data directly here in sync mode
        if profile_data and profile_data[0].get("role") == "admin":
            is_admin = True
            logger.info(f"User {user_id} confirmed as admin.")
        elif profile_data:
            logger.warning(
                f"User {user_id} found but role is not admin (role: {profile_data.get('role')}). Access denied."
            )
        else:
            logger.warning(
                f"Profile not found for user ID: {user_id}. Denying admin access."
            )

    except Exception as e:
        logger.error(
            f"Database error while checking admin role for user {user_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not verify user permissions due to a database error.",
        )

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges. Admin role required.",
        )

    return current_user


class UploadRequest(BaseModel):
    bucket: str = Field(..., description="Bucket where to upload the file.")
    folder: str | None = Field(
        None, description="Folder name to create (can be empty for root)."
    )
    data: Dict[str, Any] = Field(
        ...,
        description="Data to upload (keys are relative paths, values are string content).",
    )


def upload_to_bucket(
    supabase: Client, upload_data: UploadRequest
) -> List[Dict[str, Any]]:
    """
    Uploads data (text or JSON) to a bucket.

    Args:
        supabase: Supabase client instance
        upload_data: UploadRequest object containing bucket name, folder, and data.
                     Data values can be strings or JSON-serializable Python objects (dicts, lists).

    Returns:
        A list of dictionaries, each containing the path and response for a successfully uploaded file.

    Raises:
        HTTPException: If any file upload fails or data serialization fails.
    """
    storage = supabase.storage.from_(upload_data.bucket)
    responses = []
    errors = []

    for relative_path, content in upload_data.data.items():
        folder_part = (
            upload_data.folder.strip("/")
            if upload_data.folder
            else datetime.datetime.now().strftime("%Y-%m-%d")
        )
        relative_part = relative_path.strip("/")
        full_path = f"{folder_part}/{relative_part}" if folder_part else relative_part
        full_path = full_path.lstrip("/")

        content_bytes: bytes
        content_type: str

        try:
            # --- Handle different content types ---
            if isinstance(content, (dict, list)):
                # If it's a dict or list, assume JSON
                logger.info(f"Serializing JSON data for path: {full_path}")
                # Serialize using json.dumps, indent for readability (optional)
                content_string = json.dumps(content, indent=2)
                content_bytes = content_string.encode("utf-8")
                content_type = "application/json"
            elif isinstance(content, str):
                # If it's a string, encode directly
                logger.info(f"Encoding string data for path: {full_path}")
                content_bytes = content.encode("utf-8")
                # Guess content type from extension, default to text/plain
                guessed_type, _ = mimetypes.guess_type(full_path)
                content_type = guessed_type or "text/plain"
                logger.info(f"Guessed content type for {full_path}: {content_type}")
            else:
                # Handle other potential types if necessary, or raise error
                logger.warning(
                    f"Unsupported content type for path '{full_path}': {type(content)}. Converting to string."
                )
                # Fallback: try converting to string and encoding
                content_bytes = str(content).encode("utf-8")
                content_type = "text/plain"  # Default for unknown types
            # --- End Handle different content types ---

        except TypeError as e:
            logger.error(
                f"Failed to serialize or encode content for path '{full_path}': {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=400,  # Bad request data
                detail=f"Invalid data type for path '{full_path}'. Could not serialize/encode: {str(e)}",
            ) from e
        except Exception as e:  # Catch potential json.dumps errors too
            logger.error(
                f"Error processing content for path '{full_path}': {e}", exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Error processing content for path '{full_path}': {str(e)}",
            ) from e

        logger.info(
            f"Attempting to upload to bucket '{upload_data.bucket}', path: '{full_path}', content-type: '{content_type}'"
        )
        try:
            response = storage.upload(
                path=full_path,
                file=content_bytes,
                file_options={
                    "content-type": content_type,  # Use determined content type
                    "upsert": "true",
                },
            )
            logger.info(
                f"Successfully uploaded to '{full_path}'. Raw Response: {response}"
            )
            responses.append({"path": full_path, "response_data": repr(response)})

        except Exception as e:
            logger.error(
                f"Failed to upload file to path '{full_path}': {e}", exc_info=True
            )
            errors.append({"path": full_path, "error": str(e)})
            raise HTTPException(
                status_code=500, detail=f"Failed to upload file '{full_path}': {str(e)}"
            ) from e

    return responses


def download_from_bucket(supabase: Client, bucket_name: str, file_path: str):
    pass


# Define the expected timestamp format in folder names
FOLDER_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S_%f"


def parse_folder_timestamp(folder_item: Dict[str, Any]) -> datetime:
    # Treat non-folders as minimum date for sorting purposes
    if folder_item.get("id") is not None:
        return datetime.min

    folder_name = folder_item.get("name", "")
    try:
        # Attempt to parse the timestamp from the folder name
        return datetime.strptime(folder_name, FOLDER_TIMESTAMP_FORMAT)
    except (ValueError, TypeError):
        logger.warning(
            f"Could not parse timestamp from folder name: '{folder_name}'. Treating as oldest."
        )
        return datetime.min  # Return min datetime for sorting if parsing fails


# Return a list of sorted folders and files (descending order for folders, sorted by name for files)
def list_files_in_folder(
    supabase: Client,
    bucket_name: str = "scraper-data",
    folder_path: Optional[str] = None,  # Optional: Specify folder directly
    target_most_recent: bool = False,  # Optional: Target the most recent timestamped folder
    files_only: bool = True,  # Optional: Return only files, exclude subfolders
) -> List[Dict[str, Any]]:
    """
    Lists files within a specific folder in a Supabase bucket.

    Can target a specific folder path or automatically find the most
    recently created timestamped folder at the root level.

    Args:
        supabase: Initialized Supabase client.
        bucket_name: Name of the bucket.
        folder_path: Exact path of the folder to list files from.
                     If provided, target_most_recent is ignored.
        target_most_recent: If True and folder_path is None, finds the folder
                            at the root with the most recent timestamp name
                            (format: YYYYMMDD_HHMMSS_ffffff) and lists its contents.
        files_only: If True, filters the result to include only files (items with an id).

    Returns:
        A list of dictionaries representing the items (files or all)
        found within the target folder. Returns empty list if folder
        not found, empty, or errors occur during listing.

    Raises:
        ValueError: If target_most_recent is True and no valid
                    timestamped folders are found at the root.
    """
    target_path: str | None = folder_path

    if not target_path and target_most_recent:
        logger.info(f"Finding most recent folder in bucket '{bucket_name}'...")
        try:
            # List items at the root to find folders
            root_items = supabase.storage.from_(bucket_name).list(
                path=""
            )  # Explicitly list root
            if not root_items:
                logger.warning(f"Bucket '{bucket_name}' is empty or inaccessible.")
                return []

            # Filter for folders (id is None) and parse timestamps
            # Sort by timestamp descending (most recent first)
            sorted_folders = sorted(
                root_items,
                key=parse_folder_timestamp,  # Use helper function as key
                reverse=True,
            )

            # Find the first item that is actually a folder with a valid timestamp
            most_recent_folder = None
            for item in sorted_folders:
                # Check if it's a folder (id is None) AND if parsing succeeded (timestamp > min)
                if (
                    item.get("id") is None
                    and parse_folder_timestamp(item) > datetime.min
                ):
                    most_recent_folder = item
                    break  # Found the most recent valid one

            if not most_recent_folder:
                logger.error(
                    f"No valid timestamped folders found at the root of bucket '{bucket_name}'."
                )
                raise ValueError(
                    f"No valid timestamped folders found in bucket '{bucket_name}'."
                )

            target_path = most_recent_folder.get("name")
            logger.info(f"Identified most recent folder: '{target_path}'")

        except Exception as e:
            logger.error(
                f"Error finding most recent folder in '{bucket_name}': {e}",
                exc_info=True,
            )
            # Re-raise or return empty list depending on desired behavior
            # raise e # Option 1: Propagate error
            return []  # Option 2: Return empty on error finding folder

    # If no path determined by either argument or finding most recent, list root
    if target_path is None:
        target_path = ""  # Default to root if nothing else specified
        logger.info(f"No specific folder targeted, listing root of '{bucket_name}'.")

    logger.info(f"Listing items in bucket '{bucket_name}' at path: '{target_path}'")
    try:
        response = supabase.storage.from_(bucket_name).list(path=target_path)
        if not response:
            # This could mean the folder doesn't exist or is empty
            logger.warning(
                f"No items found in path '{target_path}' or path does not exist in bucket '{bucket_name}'."
            )
            return []

        if files_only:
            # Filter out items that look like folders (id is None)
            files = [item for item in response if item.get("id") is not None]
            logger.info(f"Found {len(files)} file(s) in path '{target_path}'.")
            return files
        else:
            logger.info(
                f"Found {len(response)} item(s) (files and folders) in path '{target_path}'."
            )
            return response

    except Exception as e:
        logger.error(
            f"Error listing items in bucket '{bucket_name}' at path '{target_path}': {e}",
            exc_info=True,
        )
        return []
