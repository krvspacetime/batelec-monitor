import datetime
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from supabase import Client
from webdriver_manager.chrome import ChromeDriverManager

from db.supabase import UploadRequest, upload_to_bucket

# --- Configuration ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
COOKIE_BUTTON_XPATHS = [
    "//div[@aria-label='Allow all cookies']//div[@role='button']",
    "//button[contains(., 'Allow essential and optional cookies')]",
    "//button[contains(., 'Accept All')]",
    "//button[contains(., 'Allow all')]",
]
LOGIN_CLOSE_XPATHS = [
    "//div[@aria-label='Close' and @role='button']",
    "//div[@aria-label='Close dialog' and @role='button']",
]
# Selectors for post content
POST_TEXT_SELECTOR_1 = ".//div[@data-ad-preview='message']"
POST_TEXT_SELECTOR_2 = ".//div[contains(@style, 'text-align: start;') and @dir='auto']"
POST_TEXT_CHILD_SPANS = ".//span[contains(@class, 'x193iq5w')]"
POST_IMAGE_SELECTOR = ".//img[contains(@src, 'https')]"
SEE_MORE_BUTTON_SELECTORS = [
    ".//div[text()='See more']",
    ".//span[text()='See more']",
    ".//div[contains(text(), 'See more')]",
]
TIMESTAMP_SELECTORS = [
    ".//a[contains(@href, '/posts/') and contains(@aria-label, '')]",  # Post timestamp link
    ".//span[contains(@class, 'x4k7w5x') and contains(@class, 'x1h91t0o')]",  # Timestamp span
    ".//a[contains(@class, 'x1i10hfl') and contains(@href, '/permalink/')]",  # Permalink
]

BUCKET_NAME = "scraper-data"


# --- Logging Configuration ---
def setup_logger(log_file: Optional[str] = None, level=logging.INFO) -> logging.Logger:
    """Set up and return a configured logger"""
    logger = logging.getLogger("fb_scraper")
    logger.setLevel(level)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create file handler if log_file is specified
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Initialize logger
logger = setup_logger()


# --- File Handling ---
def safe_create_file(
    filename: Union[str, Path], data: Any, overwrite: bool = False
) -> Union[str, Path]:
    """Safely creates a file, avoiding overwriting existing files unless specified."""
    # Convert Path to string if needed for processing
    filename_str = str(filename) if isinstance(filename, Path) else filename

    # Handle direct overwrite case
    if overwrite:
        if isinstance(filename, Path):
            # Ensure parent directory exists
            filename.parent.mkdir(parents=True, exist_ok=True)

            if filename_str.endswith(".json"):
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            else:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(data)
        else:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filename_str) or ".", exist_ok=True)

            if filename_str.endswith(".json"):
                with open(filename_str, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            else:
                with open(filename_str, "w", encoding="utf-8") as f:
                    f.write(data)
        return filename

    # Handle non-overwrite case with unique filename generation
    base_name, extension = os.path.splitext(filename_str)
    extension = extension.lstrip(".")

    counter = 1
    while True:
        new_filename = f"{base_name}_{counter}.{extension}"
        if not os.path.exists(new_filename):
            # Ensure directory exists
            os.makedirs(os.path.dirname(new_filename) or ".", exist_ok=True)

            if extension == "json":
                with open(new_filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            else:
                with open(new_filename, "w", encoding="utf-8") as f:
                    f.write(data)
            return new_filename
        counter += 1


# --- Browser Interaction ---
def close_popups(
    driver: webdriver.Chrome,
    wait_time: int = 3,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Attempts to find and click known pop-up buttons with improved error handling."""
    if logger is None:
        logger = logging.getLogger("fb_scraper")

    # Try closing cookie banners
    for xpath in COOKIE_BUTTON_XPATHS:
        try:
            cookie_button = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            logger.info(f"Found and clicking cookie button: {xpath}")
            cookie_button.click()
            time.sleep(1)
            logger.info("Cookie banner likely closed.")
            break
        except (NoSuchElementException, TimeoutException):
            logger.debug(f"Cookie button not found or clickable: {xpath}")
        except ElementClickInterceptedException:
            logger.warning(f"Cookie button found but click was intercepted: {xpath}")
            # Try JavaScript click as fallback
            try:
                driver.execute_script(
                    "arguments[0].click();", driver.find_element(By.XPATH, xpath)
                )
                logger.info("Used JavaScript click for cookie button")
                time.sleep(1)
                break
            except Exception as js_e:
                logger.warning(f"JavaScript click also failed: {js_e}")
        except Exception as e:
            logger.warning(f"Error clicking cookie button {xpath}: {e}")

    # Try closing login popups
    for xpath in LOGIN_CLOSE_XPATHS:
        try:
            close_button = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            logger.info(f"Found and clicking login close button: {xpath}")
            close_button.click()
            time.sleep(1)
            logger.info("Login popup likely closed.")
            break
        except (NoSuchElementException, TimeoutException):
            logger.debug(f"Login close button not found or clickable: {xpath}")
        except ElementClickInterceptedException:
            logger.warning(f"Login button found but click was intercepted: {xpath}")
            # Try JavaScript click as fallback
            try:
                driver.execute_script(
                    "arguments[0].click();", driver.find_element(By.XPATH, xpath)
                )
                logger.info("Used JavaScript click for login close button")
                time.sleep(1)
                break
            except Exception as js_e:
                logger.warning(f"JavaScript click also failed: {js_e}")
        except Exception as e:
            logger.warning(f"Error clicking login close button {xpath}: {e}")


def click_see_more_buttons(
    driver: webdriver.Chrome, post_element, logger: Optional[logging.Logger] = None
) -> bool:
    """Attempts to click 'See more' buttons within a post to expand text content."""
    if logger is None:
        logger = logging.getLogger("fb_scraper")

    clicked_any = False

    for selector in SEE_MORE_BUTTON_SELECTORS:
        try:
            see_more_buttons = post_element.find_elements(By.XPATH, selector)
            for button in see_more_buttons:
                if button.is_displayed() and button.is_enabled():
                    logger.info(f"Found 'See more' button using selector: {selector}")
                    try:
                        button.click()
                        clicked_any = True
                        logger.info("Clicked 'See more' button successfully")
                        time.sleep(1)  # Wait for content to expand
                    except ElementClickInterceptedException:
                        logger.warning(
                            "'See more' button click was intercepted, trying JavaScript"
                        )
                        try:
                            driver.execute_script("arguments[0].click();", button)
                            clicked_any = True
                            logger.info("Used JavaScript to click 'See more' button")
                            time.sleep(1)  # Wait for content to expand
                        except Exception as js_e:
                            logger.warning(f"JavaScript click also failed: {js_e}")
        except Exception as e:
            logger.debug(
                f"Error finding or clicking 'See more' buttons with selector {selector}: {e}"
            )

    return clicked_any


# --- Data Extraction ---
def extract_timestamp(
    post_element, logger: Optional[logging.Logger] = None
) -> Optional[str]:
    """Extracts timestamp information from a post."""
    if logger is None:
        logger = logging.getLogger("fb_scraper")

    for selector in TIMESTAMP_SELECTORS:
        try:
            timestamp_elements = post_element.find_elements(By.XPATH, selector)
            for element in timestamp_elements:
                # Try to get the timestamp from aria-label or text content
                timestamp = element.get_attribute("aria-label") or element.text
                if timestamp and not timestamp.isspace():
                    logger.info(f"Found timestamp: {timestamp}")
                    return timestamp
        except Exception as e:
            logger.debug(f"Error extracting timestamp with selector {selector}: {e}")

    logger.debug("Could not extract timestamp from post")
    return None


def extract_post_data(
    driver: webdriver.Chrome, post_element, logger: Optional[logging.Logger] = None
) -> Dict:
    """Extracts text, image links, and timestamp from a single post WebElement with improved handling."""
    if logger is None:
        logger = logging.getLogger("fb_scraper")

    post_data = {"text": "", "img_links": [], "timestamp": None}

    # Try to click 'See more' buttons to expand content
    click_see_more_buttons(driver, post_element, logger)

    # --- Extract Text ---
    try:
        # Try primary selector first
        text_elements = post_element.find_elements(By.XPATH, POST_TEXT_SELECTOR_1)
        if text_elements:
            post_data["text"] = "\n".join(
                [elem.text for elem in text_elements if elem.text]
            ).strip()
        else:
            # Try secondary selector
            text_elements = post_element.find_elements(By.XPATH, POST_TEXT_SELECTOR_2)
            if text_elements:
                post_data["text"] = "\n".join(
                    [elem.text for elem in text_elements if elem.text]
                ).strip()
            else:
                # Try finding text within specific spans as a fallback
                span_elements = post_element.find_elements(
                    By.XPATH, POST_TEXT_CHILD_SPANS
                )
                # Filter out potential button text like "See more" - simplistic filter
                post_data["text"] = "\n".join(
                    [
                        span.text
                        for span in span_elements
                        if span.text and len(span.text) > 15
                    ]
                ).strip()

        # Handle potential "See more" buttons within the text block
        if post_data["text"]:
            # Basic cleanup, remove trailing "See more" if it exists alone on the last line
            lines = post_data["text"].split("\n")
            if lines and lines[-1].strip().lower() == "see more":
                post_data["text"] = "\n".join(lines[:-1]).strip()

        if not post_data["text"]:
            logger.debug("Could not find post text using known selectors.")

    except NoSuchElementException:
        logger.debug("Text container not found for a post.")
    except Exception as e:
        logger.warning(f"Error extracting text from post: {e}")

    # --- Extract Image Links ---
    try:
        image_elements = post_element.find_elements(By.XPATH, POST_IMAGE_SELECTOR)
        img_links = []
        seen_links = set()  # Avoid duplicates

        for img in image_elements:
            src = img.get_attribute("src")
            if src and src.startswith("https") and src not in seen_links:
                # Basic filter: Avoid tiny profile pics often included in post header/comments
                img_height = img.get_attribute("height")
                img_width = img.get_attribute("width")

                is_likely_profile_pic = (
                    "profile" in src
                    or "avatar" in src
                    or (img_height and int(img_height) < 40)
                    or (img_width and int(img_width) < 40)
                )

                if not is_likely_profile_pic:
                    img_links.append(src)
                    seen_links.add(src)

        post_data["img_links"] = img_links
    except NoSuchElementException:
        logger.debug("Image elements not found for a post.")
    except Exception as e:
        logger.warning(f"Error extracting images from post: {e}")

    # --- Extract Timestamp ---
    post_data["timestamp"] = extract_timestamp(post_element, logger)

    return post_data


# --- Main Scraper Function ---
def is_valid_url(url: str) -> bool:
    """Validate if the provided string is a valid URL."""
    try:
        result = urlparse(url)
        # Check if scheme and netloc are present
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def scrape_facebook_page(
    url: str,
    supabase: Client | None = None,
    # output_html_file and output_json_file args are now less relevant
    # if always uploading to Supabase, but keep them if local saving is optional
    # output_html_file: Optional[Union[str, Path]] = "facebook_page.html",
    # output_json_file: Optional[Union[str, Path]] = "facebook_data.json",
    target_folder: Optional[str] = None,  # Add arg for explicit folder name
    sleep_time: int = 5,
    max_scrolls: int = 15,
    headless: bool = True,
    log_file: Optional[str] = None,
    proxy: Optional[str] = None,
) -> Dict:
    """Scrapes a Facebook page, uploads data to Supabase, and returns extracted data.

    Args:
        url: Facebook page URL to scrape.
        supabase: Initialized Supabase client instance. Required for uploading.
        target_folder: Optional specific folder name in Supabase bucket.
                       If None, a timestamp-based folder will be created.
        sleep_time: Time to wait between scrolls in seconds.
        max_scrolls: Maximum number of page scrolls.
        headless: Whether to run browser in headless mode.
        log_file: Path to log file (None for console logging only).
        proxy: Proxy server to use (format: 'http://user:pass@host:port').

    Returns:
        Dictionary containing the extracted data and upload status.
    """
    # Setup logger
    logger = setup_logger(log_file)
    logger.info(f"Starting Facebook scraper for URL: {url}")

    if supabase is None:
        logger.error("Supabase client instance is required for uploading.")
        # Return an error structure consistent with the success case
        return {
            "success": False,
            "posts": [],
            "error": "Supabase client not provided.",
            "upload_info": None,
            "stats": {"start_time": datetime.datetime.now().isoformat()},
        }

    # --- Determine Target Folder Name ---
    # Use provided name or generate timestamp if None
    actual_folder_name: str
    if target_folder:
        actual_folder_name = target_folder.strip("/")
        logger.info(f"Using provided target folder: '{actual_folder_name}'")
    else:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        actual_folder_name = now_utc.strftime("%Y%m%d_%H%M%S_%f")
        logger.info(f"Generated timestamp target folder: '{actual_folder_name}'")
    # --- Folder Name Determined ---

    # Configure browser options (keep your existing options setup)
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    # ... (add all your other options: gpu, window-size, sandbox, user-agent etc.) ...
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={USER_AGENT}")
    options.add_argument("--disable-notifications")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--lang=en-US,en;q=0.9")
    prefs = {"intl.accept_languages": "en-US,en;q=0.9"}
    options.add_experimental_option("prefs", prefs)
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
        logger.info(f"Using proxy: {proxy}")

    # Initialize result data structure
    result = {
        "success": False,
        "posts": [],
        "error": None,
        "upload_info": {  # Store upload details here
            "bucket": BUCKET_NAME,
            "folder": actual_folder_name,
            "uploaded_files": [],
        },
        # "html_file": None, # Less relevant now, maybe store path within bucket
        # "json_file": None, # Less relevant now, maybe store path within bucket
        "stats": {
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": None,
            "duration_seconds": None,
            "posts_found": 0,
            "scrolls_performed": 0,
        },
    }

    # Validate URL before proceeding
    if not is_valid_url(url):
        error_msg = f"Invalid URL provided: {url}"
        logger.error(error_msg)
        result["error"] = error_msg
        return result

    start_time = time.time()
    driver = None

    try:
        # Initialize WebDriver (keep your existing setup)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # --- Load Page & Scroll ---
        logger.info(f"Loading page: {url}")
        driver.get(url)
        time.sleep(sleep_time)
        logger.info("Attempting to close initial pop-ups...")
        close_popups(driver, wait_time=5, logger=logger)
        time.sleep(2)

        last_height = driver.execute_script("return document.body.scrollHeight")
        scrolls = 0
        no_change_streak = 0
        while scrolls < max_scrolls:
            logger.info(f"Scrolling attempt {scrolls + 1}/{max_scrolls}")
            close_popups(
                driver, wait_time=2, logger=logger
            )  # Close popups during scroll too
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(sleep_time)
            new_height = driver.execute_script("return document.body.scrollHeight")
            # ... (keep your scroll height check logic) ...
            if new_height == last_height:
                no_change_streak += 1
                logger.warning(
                    f"Scroll height did not change. Streak: {no_change_streak}"
                )
                if no_change_streak >= 3:
                    logger.warning(
                        "Scroll height unchanged for 3 consecutive scrolls. Ending scroll."
                    )
                    break
            else:
                last_height = new_height
                no_change_streak = 0
                logger.info(f"Scroll height increased to {new_height}.")
            scrolls += 1
            result["stats"]["scrolls_performed"] = scrolls
        time.sleep(3)  # Final wait

        # --- Extract Post Data ---
        logger.info("Finished scrolling. Finding post elements for data extraction...")
        post_elements = driver.find_elements(By.XPATH, "//div[@role='article']")
        logger.info(f"Found {len(post_elements)} final post elements to process.")
        result["stats"]["posts_found"] = len(post_elements)

        all_posts_data = []
        for i, post_element in enumerate(post_elements):
            logger.info(f"Processing post {i+1}/{len(post_elements)}")
            post_data = extract_post_data(driver, post_element, logger)
            if post_data.get("text") or post_data.get("img_links"):
                all_posts_data.append(post_data)
            else:
                logger.warning(f"Post {i+1} did not yield text or images.")

        # --- Upload Extracted Post Data (JSON) ---
        if all_posts_data:
            # Define the structure for the JSON file content
            output_data_json = {
                "url": url,
                "scraped_at": datetime.datetime.now().isoformat(),
                "posts": all_posts_data,
            }
            # Define the filename within the bucket folder
            json_filename = "extracted_posts.json"
            logger.info(
                f"Preparing to upload '{json_filename}' to folder '{actual_folder_name}'"
            )

            # Create the UploadRequest object for the JSON data
            request_json = UploadRequest(
                bucket=BUCKET_NAME,
                folder=actual_folder_name,  # Use the determined folder name
                data={
                    json_filename: output_data_json
                },  # Adhere to Dict[str, Any] structure
            )
            # Call the upload function
            upload_response = upload_to_bucket(supabase, request_json)
            logger.info(f"JSON data uploaded successfully. Response: {upload_response}")
            # Add uploaded file path to results
            if upload_response and result["upload_info"]:
                result["upload_info"]["uploaded_files"].extend(
                    [resp.get("path") for resp in upload_response if resp.get("path")]
                )

        else:
            logger.warning("No post data extracted to upload.")

        # --- Upload Full Page HTML ---
        logger.info("Getting full page source for HTML upload...")
        page_source = driver.page_source
        if page_source:
            # Define the filename for the HTML file
            html_filename = "page_source.html"
            logger.info(
                f"Preparing to upload '{html_filename}' to folder '{actual_folder_name}'"
            )

            # Create the UploadRequest object for the HTML data
            request_html = UploadRequest(
                bucket=BUCKET_NAME,
                folder=actual_folder_name,  # Use the SAME determined folder name
                data={html_filename: page_source},  # Adhere to Dict[str, Any] structure
            )
            # Call the upload function
            upload_response_html = upload_to_bucket(supabase, request_html)
            logger.info(
                f"HTML data uploaded successfully. Response: {upload_response_html}"
            )
            # Add uploaded file path to results
            if upload_response_html and result["upload_info"]:
                result["upload_info"]["uploaded_files"].extend(
                    [
                        resp.get("path")
                        for resp in upload_response_html
                        if resp.get("path")
                    ]
                )
        else:
            logger.warning("Could not retrieve page source for HTML upload.")

        # Update final result
        result["success"] = True
        result["posts"] = all_posts_data  # Keep the extracted posts in the result

    except Exception as e:
        logger.error(
            f"An error occurred during scraping: {e}", exc_info=True
        )  # Log traceback
        result["error"] = str(e)
        # Ensure success is False if an exception occurred before it was set
        result["success"] = False

    finally:
        # Clean up
        if driver:
            driver.quit()
            logger.info("Driver closed.")

        # Update timing stats
        end_time = time.time()
        result["stats"]["end_time"] = datetime.datetime.now().isoformat()
        result["stats"]["duration_seconds"] = round(end_time - start_time, 2)

        logger.info(
            f"Scraping completed in {result['stats']['duration_seconds']} seconds. Success: {result['success']}"
        )
        return result
