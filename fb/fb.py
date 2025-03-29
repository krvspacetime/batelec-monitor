import logging
import time

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="selenium.log",
)
# --- Configuration ---
# Use a realistic user agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
# Selectors for potential pop-up elements (these might change, inspect manually if needed)
COOKIE_BUTTON_XPATHS = [
    "//div[@aria-label='Allow all cookies']//div[@role='button']",  # Common variations
    "//button[contains(., 'Allow essential and optional cookies')]",
    "//button[contains(., 'Accept All')]",
    "//button[contains(., 'Allow all')]",
]
LOGIN_CLOSE_XPATHS = [
    "//div[@aria-label='Close' and @role='button']",  # Common close button for login popups
]
# --- End Configuration ---


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
            time.sleep(1)  # Short pause after click
            logging.info("Cookie banner likely closed.")
            # Once one is clicked, assume the job is done for cookies
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
            # Once one is clicked, assume the job is done for login popups
            break
        except (NoSuchElementException, TimeoutException):
            logging.debug(f"Login close button not found or clickable: {xpath}")
        except Exception as e:
            logging.warning(f"Error clicking login close button {xpath}: {e}")


def scrape_facebook_page(
    url: str,
    output_file: str = "facebook_page.html",
    sleep_time: int = 5,  # Increased default sleep time
    max_scrolls: int = 15,
):
    """Scrapes a Facebook page by scrolling and saves the HTML content."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  # Use new headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")  # Set a reasonable window size
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={USER_AGENT}")
    # Disable notifications that can interfere
    options.add_argument("--disable-notifications")
    # Experimental flags to appear less like automation
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    # Helps reduce detection
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    try:
        logging.info(f"Loading page: {url}")
        driver.get(url)
        time.sleep(sleep_time)  # Initial wait for page load & potential popups

        # --- Attempt to close initial popups ---
        logging.info("Attempting to close initial pop-ups...")
        close_popups(driver, wait_time=5)  # Give more time for initial popups
        time.sleep(2)  # Wait a bit after potential clicks

        last_height = driver.execute_script("return document.body.scrollHeight")
        scrolls = 0
        no_change_streak = 0

        while scrolls < max_scrolls:
            logging.info(f"Scrolling attempt {scrolls + 1}/{max_scrolls}")

            # --- Attempt to close popups that might appear after scrolling ---
            close_popups(driver, wait_time=2)  # Quicker check during scroll loop

            # Scroll down to the bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait for page to load
            time.sleep(sleep_time)

            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")

            # Also, check for posts as a secondary measure (optional, mainly for logging)
            try:
                posts = driver.find_elements(By.XPATH, "//div[@role='article']")
                logging.info(f"Found {len(posts)} potential posts elements.")
            except Exception:
                logging.warning("Could not find post elements during scroll.")

            if new_height == last_height:
                no_change_streak += 1
                logging.warning(
                    f"Scroll height did not change. Streak: {no_change_streak}"
                )
                # If height hasn't changed for a few scrolls, assume end of content or blockage
                if no_change_streak >= 3:
                    logging.warning(
                        "Scroll height unchanged for 3 consecutive scrolls. Ending scroll."
                    )
                    break
            else:
                last_height = new_height
                no_change_streak = 0  # Reset streak if height changes
                logging.info(f"Scroll height increased to {new_height}.")

            scrolls += 1

        # Optionally wait a final time for everything to settle
        time.sleep(3)

        # Get full page source after scrolling
        logging.info("Finished scrolling. Getting page source...")
        page_source = driver.page_source

        # Save the page source to an HTML file
        with open(output_file, "w", encoding="utf-8") as file:
            file.write(page_source)

        logging.info(f"Page saved as {output_file}")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        # Save page source even on error for debugging
        try:
            page_source_on_error = driver.page_source
            error_filename = f"error_{output_file}"
            with open(error_filename, "w", encoding="utf-8") as file:
                file.write(page_source_on_error)
            logging.info(f"Saved page source on error to {error_filename}")
        except Exception as e_save:
            logging.error(f"Could not save page source on error: {e_save}")

    finally:
        if "driver" in locals() and driver:
            driver.quit()
            logging.info("Driver closed.")


if __name__ == "__main__":
    scrape_facebook_page(
        "https://www.facebook.com/Batangas1ElectricCooperativeInc",
        output_file="bateleco_page.html",  # More specific filename
        sleep_time=6,  # Slightly longer wait might be needed
        max_scrolls=20,  # Increase max scrolls if you want more content
    )
