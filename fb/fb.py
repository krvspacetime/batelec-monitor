import json  # Import the json module
import logging
import os
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
COOKIE_BUTTON_XPATHS = [
    "//div[@aria-label='Allow all cookies']//div[@role='button']",
    "//button[contains(., 'Allow essential and optional cookies')]",
    "//button[contains(., 'Accept All')]",
    "//button[contains(., 'Allow all')]",
]
LOGIN_CLOSE_XPATHS = [
    "//div[@aria-label='Close' and @role='button']",
]
# Selectors for post content (relative to the main post element)
# These might need adjustment based on FB layout changes
POST_TEXT_SELECTOR_1 = (
    ".//div[@data-ad-preview='message']"  # Often contains the main text
)
POST_TEXT_SELECTOR_2 = ".//div[contains(@style, 'text-align: start;') and @dir='auto']"  # Alternative selector
POST_TEXT_CHILD_SPANS = (
    ".//span[contains(@class, 'x193iq5w')]"  # Sometimes text is split into spans
)
POST_IMAGE_SELECTOR = ".//img[contains(@src, 'https')]"  # Find img tags with https sources (filters data URIs)

# --- End Configuration ---


def safe_create_file(filename: str | Path, data: any, overwrite=False):
    """Safely creates a file, avoiding overwriting existing files."""
    if overwrite:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(data)
        return filename
    base_name, extension = filename.rsplit(".", 1)
    if extension == "html":
        counter = 1
        while True:
            new_filename = f"{base_name}_{counter}.{extension}"
            if not os.path.exists(new_filename):
                with open(new_filename, "w", encoding="utf-8") as f:
                    f.write(data)
                return new_filename
            counter += 1
    if extension == "json":
        counter = 1
        while True:
            new_filename = f"{base_name}_{counter}.{extension}"
            if not os.path.exists(new_filename):
                with open(new_filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                return new_filename
            counter += 1


def close_popups(driver, wait_time=3):
    """Attempts to find and click known pop-up buttons."""
    # Try closing cookie banners
    for xpath in COOKIE_BUTTON_XPATHS:
        try:
            cookie_button = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            logging.info(f"Found and clicking cookie button: {xpath}")
            cookie_button.click()
            time.sleep(1)
            logging.info("Cookie banner likely closed.")
            break
        except (NoSuchElementException, TimeoutException):
            logging.debug(f"Cookie button not found or clickable: {xpath}")
        except Exception as e:
            logging.warning(f"Error clicking cookie button {xpath}: {e}")

    # Try closing login popups
    for xpath in LOGIN_CLOSE_XPATHS:
        try:
            close_button = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            logging.info(f"Found and clicking login close button: {xpath}")
            close_button.click()
            time.sleep(1)
            logging.info("Login popup likely closed.")
            break
        except (NoSuchElementException, TimeoutException):
            logging.debug(f"Login close button not found or clickable: {xpath}")
        except Exception as e:
            logging.warning(f"Error clicking login close button {xpath}: {e}")


def extract_post_data(post_element):
    """Extracts text and image links from a single post WebElement."""
    post_data = {"text": "", "img_links": []}

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
        # Note: This might need more sophisticated handling if "See more" needs clicking
        if post_data["text"]:
            # Basic cleanup, remove trailing "See more" if it exists alone on the last line
            lines = post_data["text"].split("\n")
            if lines and lines[-1].strip().lower() == "see more":
                post_data["text"] = "\n".join(lines[:-1]).strip()

        if not post_data["text"]:
            logging.debug("Could not find post text using known selectors.")
            # As a last resort, get all text directly under the article, might be noisy
            # post_data["text"] = post_element.text # Use with caution

    except NoSuchElementException:
        logging.debug("Text container not found for a post.")
    except Exception as e:
        logging.warning(f"Error extracting text from post: {e}")

    # --- Extract Image Links ---
    try:
        image_elements = post_element.find_elements(By.XPATH, POST_IMAGE_SELECTOR)
        img_links = []
        seen_links = (
            set()
        )  # Avoid duplicates if same image appears multiple times in structure
        for img in image_elements:
            src = img.get_attribute("src")
            if src and src.startswith("https") and src not in seen_links:
                # Basic filter: Avoid tiny profile pics often included in post header/comments
                # This is heuristic - adjust classes/size checks if needed
                img_height = img.get_attribute("height")
                img_width = img.get_attribute("width")

                is_likely_profile_pic = (
                    "profile" in src
                    or "avatar" in src
                    or (img_height and int(img_height) < 40)
                    or (img_width and int(img_width) < 40)
                )

                # Add more filters if necessary (e.g., based on parent element classes)
                # Example: if 'story_thumbnail' in parent_classes: continue

                if not is_likely_profile_pic:
                    img_links.append(src)
                    seen_links.add(src)

        post_data["img_links"] = img_links
    except NoSuchElementException:
        logging.debug("Image elements not found for a post.")
    except Exception as e:
        logging.warning(f"Error extracting images from post: {e}")

    return post_data


def scrape_facebook_page(
    url: str,
    output_html_file: str = "facebook_page.html",
    output_json_file: str = "facebook_data.json",  # New parameter for JSON output
    sleep_time: int = 5,
    max_scrolls: int = 15,
):
    """
    Scrapes a Facebook page, saves HTML, and extracts post data (text, images) to JSON.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={USER_AGENT}")
    options.add_argument("--disable-notifications")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # Set language preference to English to make selectors more predictable (optional)
    options.add_argument("--lang=en-US,en;q=0.9")
    prefs = {"intl.accept_languages": "en-US,en;q=0.9"}
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    all_posts_data = []  # Initialize list to store data for all posts

    try:
        logging.info(f"Loading page: {url}")
        driver.get(url)
        time.sleep(sleep_time)

        logging.info("Attempting to close initial pop-ups...")
        close_popups(driver, wait_time=5)
        time.sleep(2)

        last_height = driver.execute_script("return document.body.scrollHeight")
        scrolls = 0
        no_change_streak = 0

        while scrolls < max_scrolls:
            logging.info(f"Scrolling attempt {scrolls + 1}/{max_scrolls}")
            close_popups(driver, wait_time=2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(sleep_time)

            new_height = driver.execute_script("return document.body.scrollHeight")
            try:
                current_posts_count = len(
                    driver.find_elements(By.XPATH, "//div[@role='article']")
                )
                logging.info(
                    f"Found approx {current_posts_count} potential post elements on page."
                )
            except Exception:
                logging.warning("Could not count post elements during scroll.")

            if new_height == last_height:
                no_change_streak += 1
                logging.warning(
                    f"Scroll height did not change. Streak: {no_change_streak}"
                )
                if no_change_streak >= 3:
                    logging.warning(
                        "Scroll height unchanged for 3 consecutive scrolls. Ending scroll."
                    )
                    break
            else:
                last_height = new_height
                no_change_streak = 0
                logging.info(f"Scroll height increased to {new_height}.")

            scrolls += 1

        time.sleep(3)  # Final wait

        # --- Extract Post Data After Scrolling ---
        logging.info("Finished scrolling. Finding post elements for data extraction...")
        post_elements = driver.find_elements(By.XPATH, "//div[@role='article']")
        logging.info(f"Found {len(post_elements)} final post elements to process.")

        for i, post_element in enumerate(post_elements):
            logging.info(f"Processing post {i+1}/{len(post_elements)}")
            post_data = extract_post_data(post_element)
            # Only add if we actually found some text or images
            if post_data.get("text") or post_data.get("img_links"):
                all_posts_data.append(post_data)
            else:
                logging.warning(
                    f"Post {i+1} did not yield text or images with current selectors."
                )

        # --- Save Extracted Data to JSON ---
        if all_posts_data:
            # Structure the data as requested: {"posts": [list_of_post_dicts]}
            output_data = {"posts": all_posts_data}
            filename = safe_create_file(output_json_file, output_data)
            logging.info(f"JSON data saved as {filename}")
        else:
            logging.warning("No post data extracted to save to JSON.")

        # --- Save Full Page HTML ---
        logging.info("Getting full page source...")
        page_source = driver.page_source

        filename = safe_create_file(output_html_file, page_source)
        logging.info(f"Page HTML saved as {filename}")

    except Exception as e:
        logging.error(f"An error occurred during scraping: {e}")
    finally:
        if "driver" in locals() and driver:
            driver.quit()
            logging.info("Driver closed.")


if __name__ == "__main__":
    scrape_facebook_page(
        url="https://www.facebook.com/Batangas1ElectricCooperativeInc",
        output_html_file="fb/bateleco_page.html",
        output_json_file="fb/bateleco_data.json",  # Specify JSON filename
        sleep_time=6,
        max_scrolls=20,  # You might want fewer scrolls if focusing only on data
    )
