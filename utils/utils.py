import json
import os
import glob
from pathlib import Path
from urllib.parse import quote

CACHE_DIR = "cache"


def make_safe_filename(filename: str) -> str:
    """
    Make a filename URL-safe by replacing spaces and special characters.

    Args:
        filename (str): Original filename

    Returns:
        str: URL-safe filename
    """
    # Replace spaces with underscores
    safe_filename = filename.replace(" ", "_")
    # URL encode the filename to handle special characters
    return quote(safe_filename, safe="_")


def cache_to_file(data: dict, filename: str | Path) -> None:
    try:
        # Ensure the cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Create the full path with safe filename
        full_path = os.path.join(CACHE_DIR, make_safe_filename(str(filename)))

        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        raise Exception(f"Failed to cache data: {e}")


def get_most_recent_json_file(directory="."):
    """
    Get the most recently modified JSON file in the specified directory.

    Args:
        directory (str): Directory to search for JSON files. Defaults to current directory.

    Returns:
        str: Path to the most recently modified JSON file, or None if no JSON files found.
    """
    json_files = glob.glob(os.path.join(directory, "*.json"))
    if not json_files:
        return None

    # Sort files by modification time (most recent first)
    json_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return json_files[0]


def get_cached_data(filename: str | None = None) -> dict:
    try:
        if filename is None:
            # Find the most recently modified JSON file in the cache directory
            if not os.path.exists(CACHE_DIR):
                # Create it if it doesn't exist
                os.makedirs(CACHE_DIR)

            most_recent_file = get_most_recent_json_file(CACHE_DIR)
            if most_recent_file is None:
                raise Exception("No cached JSON files found in the cache directory")

            with open(most_recent_file, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(
                os.path.join(CACHE_DIR, make_safe_filename(str(filename))),
                "r",
                encoding="utf-8",
            ) as f:
                return json.load(f)
    except Exception as e:
        raise Exception(f"Failed to get cached data: {e}")
