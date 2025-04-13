

import os
import time
import json
import logging
import re
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from urllib.parse import urljoin

# --- Configuration ---
# !! IMPORTANT: Use environment variables or a secure config file in real applications !!
INSTAGRAM_USERNAME = "jugganuts5"
INSTAGRAM_PASSWORD = "Prevz1135"

os.environ["PATH"] += r"C:/seleniumdriver"
# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instagram_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Choose Target Page Type ---
TARGET_PAGE_URL = "https://www.instagram.com/explore/tags/pythonprogramming/"

# --- Scraping Parameters ---
MAX_POST_URLS_TO_SCRAPE = 50
MAX_SCROLL_ATTEMPTS = 20
SCROLL_PAUSE_TIME = 3.5

LOGIN_URL = "https://www.instagram.com/accounts/login/"
INSTAGRAM_BASE_URL = "https://www.instagram.com/"
IMPLICIT_WAIT_TIMEOUT = 5
EXPLICIT_WAIT_TIMEOUT = 20
SHORT_DELAY = 2

# New constants for cookies
COOKIES_FILE = "instagram_cookies.pkl"
SESSION_TIMEOUT = 3 * 24 * 60 * 60  # 3 days in seconds


def get_chrome_options():
    """Sets up Chrome options for Selenium."""
    options = webdriver.ChromeOptions()
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    return options


def setup_driver():
    """Initializes and returns the Selenium WebDriver."""
    logger.info("Setting up Chrome WebDriver...")
    try:
        driver = webdriver.Chrome(options=get_chrome_options())
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.implicitly_wait(IMPLICIT_WAIT_TIMEOUT)
        logger.info("WebDriver setup complete.")
        return driver
    except Exception as e:
        logger.error(f"Error setting up WebDriver: {e}")
        raise


def save_cookies(driver):
    """Save cookies to file for session persistence."""
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'wb') as f:
            pickle.dump({
                'cookies': cookies,
                'timestamp': time.time()
            }, f)
        logger.info(f"Cookies saved to {COOKIES_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error saving cookies: {e}")
        return False


def load_cookies(driver):
    """Load cookies from file if they exist and are not expired."""
    try:
        if not os.path.exists(COOKIES_FILE):
            logger.info("No cookies file found.")
            return False

        with open(COOKIES_FILE, 'rb') as f:
            data = pickle.load(f)
            
        # Check if cookies are expired
        if time.time() - data['timestamp'] > SESSION_TIMEOUT:
            logger.info("Saved cookies have expired.")
            return False
            
        # Navigate to Instagram first (cookies must be added after visiting the domain)
        driver.get(INSTAGRAM_BASE_URL)
        time.sleep(1)
        
        # Add cookies to browser
        for cookie in data['cookies']:
            # Some cookies might cause issues, so we'll try each one separately
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.warning(f"Couldn't add cookie: {e}")
                
        logger.info("Cookies loaded successfully")
        return True
    except Exception as e:
        logger.error(f"Error loading cookies: {e}")
        return False


def check_login_status(driver):
    """Check if we're already logged in."""
    try:
        # Navigate to Instagram and check for elements that indicate logged-in state
        driver.get(INSTAGRAM_BASE_URL)
        time.sleep(3)  # Wait for page to load
        
        # Check if login form is present (not logged in)
        login_elements = driver.find_elements(By.NAME, "username")
        if login_elements:
            logger.info("Not logged in, login form detected.")
            return False
            
        # Check for elements that typically appear when logged in
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//svg[@aria-label='Home']"))
            )
            logger.info("Already logged in. Session is active.")
            return True
        except TimeoutException:
            logger.info("Home icon not found, assuming not logged in.")
            return False
            
    except Exception as e:
        logger.error(f"Error checking login status: {e}")
        return False


# Modified handle_2fa function with better detection methods
def handle_2fa(driver):
    """
    Handle two-factor authentication with enhanced button detection.
    """
    logger.info("Checking for 2FA requirements...")
    
    try:
        # Wait to see if we land on any 2FA-related page
        time.sleep(3)  # Give page time to load fully
        
        # Take a screenshot to help debug
        try:
            driver.save_screenshot("2fa_detection_screen.png")
            logger.info("Saved screenshot of current screen as 2fa_detection_screen.png")
        except:
            pass
            
        # Check for various indicators of being on a 2FA screen
        page_source = driver.page_source.lower()
        security_indicators = [
            "two-factor authentication",
            "2-factor authentication", 
            "verification code",
            "security code",
            "enter the code",
            "confirmation code",
            "authentication code",
            "6-digit code",
            "sent you a code"
        ]
        
        is_2fa_screen = any(indicator in page_source for indicator in security_indicators)
        
        # Also look for typical 2FA input fields
        potential_2fa_fields = driver.find_elements(By.XPATH, 
            """//input[
                @aria-label='Security Code' or 
                @name='verificationCode' or 
                @name='securityCode' or 
                @id='security_code' or
                @placeholder='Security code' or
                @placeholder='_ _ _ _ _ _' or
                contains(@id, 'verification') or
                contains(@class, 'verification') or
                contains(@id, 'security') or
                contains(@class, 'security')
            ]"""
        )
        
        if is_2fa_screen or potential_2fa_fields:
            logger.info("2FA screen detected!")
            
            # Ask user for the code
            security_code = input("\n⚠️ INSTAGRAM SECURITY CHECK: Enter the verification code sent to your email/phone: ")
            
            # Try to find the verification input field
            input_field = None
            
            # First try the fields we already found
            if potential_2fa_fields:
                input_field = potential_2fa_fields[0]
                logger.info("Using pre-identified 2FA input field")
            
            # If no field was found, try a more aggressive search
            if not input_field:
                logger.info("Searching for input field...")
                # Look for any input field that might be for verification
                all_inputs = driver.find_elements(By.TAG_NAME, 'input')
                
                # Filter for likely verification inputs (typically these are short numeric fields)
                for inp in all_inputs:
                    input_type = inp.get_attribute('type')
                    if input_type in ['text', 'number', 'tel']:
                        # This is likely our verification field
                        input_field = inp
                        logger.info("Found potential verification input field")
                        break
            
            # If we found an input field, enter the code
            if input_field:
                input_field.clear()
                for digit in security_code:
                    input_field.send_keys(digit)
                    time.sleep(0.1)  # Small delay between digits can help
                logger.info("Entered verification code")
                
                # Get and log all buttons on the page for debugging
                all_buttons = driver.find_elements(By.TAG_NAME, 'button')
                logger.info(f"Found {len(all_buttons)} buttons on the page")
                for i, btn in enumerate(all_buttons):
                    try:
                        btn_text = btn.text.strip()
                        btn_class = btn.get_attribute('class')
                        logger.info(f"Button {i}: Text='{btn_text}', Class='{btn_class}'")
                    except:
                        logger.info(f"Button {i}: [Could not get details]")
                
                # Expanded list of possible button selectors for verification
                possible_button_xpaths = [
                    "//button[contains(text(), 'Confirm')]",
                    "//button[contains(text(), 'Submit')]",
                    "//button[contains(text(), 'Verify')]",
                    "//button[contains(text(), 'Next')]",
                    "//button[contains(text(), 'Continue')]",
                    "//button[contains(., 'Confirm')]",
                    "//button[contains(., 'Submit')]",
                    "//button[contains(., 'Verify')]",
                    "//button[contains(., 'Next')]",
                    "//button[contains(., 'Continue')]",
                    "//button[contains(@class, 'submit')]",
                    "//button[contains(@class, 'confirm')]",
                    "//button[contains(@class, 'verify')]",
                    "//button[contains(@class, 'primary')]",  # Often primary buttons
                    "//button[contains(@class, 'next')]",
                    "//div[contains(@role, 'button')][contains(., 'Next')]",
                    "//div[contains(@role, 'button')][contains(., 'Confirm')]",
                    "//div[contains(@role, 'button')][contains(., 'Continue')]",
                    "//button[@type='submit']",  # General fallback
                    "//form//button",  # Any button inside a form
                    "//button[last()]"  # Last button on page as a fallback
                ]
                
                button_clicked = False
                for xpath in possible_button_xpaths:
                    try:
                        logger.info(f"Trying to find button with selector: {xpath}")
                        buttons = driver.find_elements(By.XPATH, xpath)
                        if buttons:
                            logger.info(f"Found {len(buttons)} matching buttons")
                            # Try to click the primary one (usually first or last)
                            for btn in buttons:
                                try:
                                    # Take screenshot before clicking
                                    driver.save_screenshot("before_button_click.png")
                                    logger.info(f"About to click button with text: '{btn.text}'")
                                    
                                    # Try traditional click first
                                    btn.click()
                                    button_clicked = True
                                    logger.info(f"Successfully clicked verification button")
                                    time.sleep(1)
                                    break
                                except Exception as click_err:
                                    logger.warning(f"Standard click failed: {click_err}")
                                    try:
                                        # Try JavaScript click as fallback
                                        driver.execute_script("arguments[0].click();", btn)
                                        button_clicked = True
                                        logger.info(f"Clicked button using JavaScript")
                                        time.sleep(1)
                                        break
                                    except Exception as js_err:
                                        logger.warning(f"JavaScript click also failed: {js_err}")
                            
                            if button_clicked:
                                break
                    except Exception as e:
                        logger.info(f"Selector failed: {e}")
                        continue
                
                # If we couldn't find a button, offer manual intervention
                if not button_clicked:
                    logger.warning("Could not find or click a verification button automatically.")
                    manual_proceed = input("Button not found automatically. Press Enter once you've manually clicked the button, or type 'skip' to continue without clicking: ")
                    if manual_proceed.lower() != 'skip':
                        logger.info("Proceeding after manual button click")
                        button_clicked = True
                
                # Wait to see if login proceeds
                time.sleep(5)
                
                # Take another screenshot to see the result
                driver.save_screenshot("after_verification_screen.png")
                
                # Check if we've successfully moved past the verification screen
                new_page_source = driver.page_source.lower()
                still_on_verification = any(indicator in new_page_source for indicator in security_indicators)
                
                if still_on_verification:
                    logger.warning("Still appears to be on verification screen after submitting code.")
                    
                    # One more chance for manual intervention
                    manual_continue = input("Still on verification screen. Press Enter after manually completing verification, or type 'fail' to abort: ")
                    if manual_continue.lower() == 'fail':
                        return False
                    else:
                        time.sleep(3)
                        logger.info("Continuing after manual verification")
                        return True
                else:
                    logger.info("Verification appears successful, proceeding.")
                    return True
            else:
                logger.error("Could not find verification input field")
                # Offer manual verification
                manual_option = input("Could not find verification input field. Enter 'manual' if you want to handle verification manually, or any other key to abort: ")
                if manual_option.lower() == 'manual':
                    input("Complete the verification manually, then press Enter to continue...")
                    return True
                return False
        else:
            logger.info("No 2FA screen detected, continuing with login process.")
            return True
            
    except Exception as e:
        logger.error(f"Error handling 2FA: {e}")
        # Offer manual fallback
        manual_fallback = input("Error in 2FA handling. Enter 'manual' to continue after manual verification, or any other key to abort: ")
        if manual_fallback.lower() == 'manual':
            input("Complete the verification manually, then press Enter to continue...")
            return True
        return False

# Modified login_instagram function to better handle the 2FA flow
def login_instagram(driver, username, password):
    """Logs into Instagram with improved support for 2FA."""
    logger.info(f"Navigating to login page: {LOGIN_URL}")
    driver.get(LOGIN_URL)
    time.sleep(SHORT_DELAY)

    try:
        logger.info("Entering login credentials...")
        
        # Wait for login page to load and find username field
        user_field = WebDriverWait(driver, EXPLICIT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        user_field.send_keys(username)
        time.sleep(0.5 + (time.time() % 1))

        # Find and fill password field
        pass_field = driver.find_element(By.NAME, "password")
        pass_field.send_keys(password)
        time.sleep(0.7 + (time.time() % 1))

        # Find and click login button
        login_button_xpath = "//button[@type='submit']"
        login_button = WebDriverWait(driver, EXPLICIT_WAIT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, login_button_xpath))
        )
        login_button.click()
        logger.info("Login submitted. Waiting for response...")
        
        # Take a screenshot after login attempt
        try:
            time.sleep(3)  # Give time for page transition
            driver.save_screenshot("after_login_screen.png")
            logger.info("Saved screenshot of post-login screen")
        except:
            pass

        # Extended wait time to see what happens after login
        time.sleep(5)
        
        # Check for various challenges Instagram might present
        if "challenge" in driver.current_url:
            logger.info("Detected challenge page in URL.")
            # This could be various challenge types including 2FA, suspicious login, etc.
            
        # Handle 2FA specifically 
        if not handle_2fa(driver):
            logger.warning("2FA handling unsuccessful or was not needed.")
            # We'll continue anyway as it might have worked despite our detection failing
        
        # Now check if we're actually logged in
        logged_in = False
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//svg[@aria-label='Home'] | //a[@href='/'] | //a[contains(@href, '/direct/inbox/')]"))
            )
            logger.info("Successfully logged in - detected Home element.")
            logged_in = True
        except TimeoutException:
            logger.warning("Could not confirm successful login by finding Home element.")
            
        # If we're not sure we're logged in, check for login failure indicators
        if not logged_in:
            error_messages = driver.find_elements(By.XPATH, "//p[contains(text(), 'incorrect') or contains(text(), 'wrong')]")
            if error_messages:
                logger.error("Login failed - incorrect credentials.")
                return False
        
        # Handle standard popups after successful login
        popups_handled = 0
        for _ in range(2):  # Try handling up to two popups (Save Info, Notifications)
            try:
                not_now_button = WebDriverWait(driver, 7).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')] | //div[@role='dialog']//button[contains(., 'Not Now')]"))
                )
                not_now_button.click()
                logger.info(f"Handled a popup ({popups_handled + 1}).")
                popups_handled += 1
                time.sleep(SHORT_DELAY)
            except (NoSuchElementException, TimeoutException):
                logger.info(f"Popup {popups_handled + 1} not found or timed out.")
                break

        # Save cookies after successful login
        save_cookies(driver)
        logger.info("Login process complete.")
        return True

    except (NoSuchElementException, TimeoutException) as e:
        logger.error(f"Login failed: Element not found or timed out - {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during login: {e}")
        return False

def scrape_post_urls_from_feed(driver, page_url, max_urls=50, scroll_attempts=20, scroll_pause_time=3.5):
    """Scrolls down a page (profile/hashtag) and extracts unique post URLs."""
    logger.info(f"Navigating to target page: {page_url}")
    driver.get(page_url)
    time.sleep(SHORT_DELAY + 1)  # Wait for initial page load

    post_urls = set()
    last_height = driver.execute_script("return document.body.scrollHeight")
    attempts_without_new_content = 0

    logger.info(f"Starting scroll process. Target: {max_urls} URLs or {scroll_attempts} scrolls.")

    for attempt in range(scroll_attempts):
        # Scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        logger.info(f"Scroll attempt {attempt + 1}/{scroll_attempts}. Pausing for {scroll_pause_time}s...")
        time.sleep(scroll_pause_time)

        # Extract links after scrolling
        links = driver.find_elements(By.TAG_NAME, 'a')
        found_new_this_scroll = False
        for link in links:
            href = link.get_attribute('href')
            # Check if href is a valid post/reel URL
            if href and (href.startswith(INSTAGRAM_BASE_URL + "p/") or href.startswith(INSTAGRAM_BASE_URL + "reel/")):
                # Use regex to be more specific
                if re.match(r"https://www.instagram.com/(p|reel)/[\w-]+/?$", href):
                    if href not in post_urls:
                        post_urls.add(href)
                        logger.info(f"Found URL ({len(post_urls)}/{max_urls}): {href}")
                        found_new_this_scroll = True

        # Check if target number of URLs reached
        if len(post_urls) >= max_urls:
            logger.info(f"Reached target number of URLs ({max_urls}). Stopping scroll.")
            break

        # Check if scroll height has changed
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            if not found_new_this_scroll:
                attempts_without_new_content += 1
                logger.warning(f"Scroll height did not change. Attempt {attempts_without_new_content} without new content.")
                if attempts_without_new_content >= 3:
                    logger.warning("Stopping scroll: Page height hasn't changed for several attempts.")
                    break
            else:
                attempts_without_new_content = 0
        else:
            attempts_without_new_content = 0

        last_height = new_height

    else:
        logger.info(f"Finished {scroll_attempts} scroll attempts.")

    logger.info(f"Found a total of {len(post_urls)} unique post URLs.")
    return list(post_urls)


def main():
    """Main function to run the scraper."""
    driver = None
    scraped_data = []
    try:
        driver = setup_driver()
        if not driver:
            return

        # Try to use saved session first
        session_valid = False
        if load_cookies(driver):
            session_valid = check_login_status(driver)
            
        # If session isn't valid, perform normal login
        if not session_valid:
            logger.info("No valid session found. Performing standard login...")
            if not login_instagram(driver, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD):
                logger.error("Login failed. Cannot proceed to scrape feed.")
                return
        else:
            logger.info("Using existing session. No need to login again.")
            
        # Now proceed with scraping
        time.sleep(SHORT_DELAY)
        post_urls = scrape_post_urls_from_feed(driver,
                                              TARGET_PAGE_URL,
                                              max_urls=MAX_POST_URLS_TO_SCRAPE,
                                              scroll_attempts=MAX_SCROLL_ATTEMPTS,
                                              scroll_pause_time=SCROLL_PAUSE_TIME)

        logger.info("\n--- Collected Post URLs ---")
        if post_urls:
            for i, url in enumerate(post_urls):
                print(f"{i + 1}: {url}")
        else:
            logger.warning("No post URLs were collected.")
        logger.info("--------------------------")

    except Exception as e:
        logger.critical(f"A critical error occurred in main execution: {e}", exc_info=True)
        if driver:
            try:
                driver.save_screenshot("critical_error_feed_scrape.png")
                logger.info("Screenshot saved as critical_error_feed_scrape.png")
            except Exception as ss_e:
                logger.error(f"Could not save screenshot: {ss_e}")

    finally:
        if driver:
            logger.info("Closing WebDriver.")
            driver.quit()


if __name__ == "__main__":
    if not INSTAGRAM_USERNAME or INSTAGRAM_USERNAME == "YOUR_TEST_USERNAME" or \
       not INSTAGRAM_PASSWORD or INSTAGRAM_PASSWORD == "YOUR_TEST_PASSWORD":
        logger.error("Please update INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD before running.")
    elif not TARGET_PAGE_URL:
        logger.error("Please set the TARGET_PAGE_URL (profile or hashtag).")
    else:
        main()