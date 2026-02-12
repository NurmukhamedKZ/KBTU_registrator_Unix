"""
UniX Platform Agent - Automatically watches lectures and completes tests.

This agent automates the process of:
1. Logging into the UniX platform
2. Navigating through lectures
3. Watching video content
4. Completing tests using AI-powered answers
"""

import os
import time
import logging
import argparse
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains

from ai_helper import AIHelper
from db_models import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("unix_agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class UniXAgent:
    """Agent for automating UniX platform lecture viewing and test completion."""
    
    BASE_URL = "https://uni-x.almv.kz"
    LESSONS_URL = f"{BASE_URL}/platform/lessons"
    
    def __init__(self, email: str, password: str, headless: bool = False):
        """
        Initialize the UniX agent.
        
        Args:
            email: UniX account email
            password: UniX account password
            headless: Run browser in headless mode
        """
        self.email = email
        self.password = password
        self.headless = headless
        self.driver = None
        self.wait = None
        self.ai_helper = None
        self.db_manager = None
        self.current_lesson_name = None  # Track current lesson for context
        self.current_lesson_url = None
        
    def setup_driver(self):
        """Set up the Chrome WebDriver with anti-detection measures."""
        options = webdriver.ChromeOptions()
        
        # Check if running on Railway/Docker (system Chrome available)
        is_railway = os.getenv("RAILWAY_ENVIRONMENT") or os.path.exists("/usr/bin/chromium")
        
        # Force headless on Railway
        if is_railway:
            self.headless = True
            logger.info("Detected Railway/Docker environment, forcing headless mode")
        
        # Basic options
        if self.headless:
            options.add_argument("--headless=new")  # Use new headless mode
        
        # Anti-detection arguments
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--mute-audio")  # Mute all audio in the browser
        
        # User agent - use a real Chrome user agent
        options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36")
        
        # Exclude automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Additional preferences
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        options.add_experimental_option("prefs", prefs)
        
        # Use system Chrome on Railway/Docker, otherwise use webdriver-manager
        if is_railway:
            chrome_path = os.getenv("CHROME_BIN", "/usr/bin/chromium")
            chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
            options.binary_location = chrome_path
            logger.info(f"Using system Chrome: {chrome_path}")
            self.driver = webdriver.Chrome(
                service=ChromeService(chromedriver_path),
                options=options
            )
        else:
            self.driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=options
            )
        
        # Set page load timeout to 60 seconds (default is too short sometimes)
        self.driver.set_page_load_timeout(60)
        
        # Execute CDP commands to hide webdriver flag
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Overwrite the `plugins` property to use a custom getter.
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Overwrite the `languages` property to use a custom getter.
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Pass the Chrome Test.
                window.chrome = {
                    runtime: {}
                };
                
                // Pass the Permissions Test.
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """
        })
        
        self.wait = WebDriverWait(self.driver, 30)
        logger.info("WebDriver initialized successfully with anti-detection")
        
    def setup_ai(self):
        """Initialize the AI helper for test answering."""
        try:
            self.ai_helper = AIHelper()
            logger.info("AI Helper initialized successfully")
        except ValueError as e:
            logger.warning(f"AI Helper not available: {e}")
            logger.warning("Tests will require manual intervention")
    
    def setup_database(self):
        """Initialize the database connection for storing questions/answers."""
        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.db_manager = DatabaseManager(database_url)
                # Test connection
                if self.db_manager.test_connection():
                    logger.info("Database connection established successfully")
                else:
                    logger.warning("Database connection test failed")
                    self.db_manager = None
            else:
                logger.info("No DATABASE_URL found, continuing without database storage")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
            logger.warning("Continuing without database storage")
            self.db_manager = None
    
    def login(self) -> bool:
        """
        Log into the UniX platform.
        
        Returns:
            True if login successful, False otherwise
        """
        LOGIN_URL = f"{self.BASE_URL}/platform/login"
        
        logger.info(f"Navigating to login page: {LOGIN_URL}")
        
        # Retry logic for initial page load
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.driver.get(LOGIN_URL)
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # 5s, 10s, 15s
                    logger.warning(f"Failed to load login page (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to load login page after {max_retries} attempts: {e}")
                    return False
        
        try:
            # Wait for page to load
            time.sleep(3)
            
            # Check if already logged in (redirected away from login)
            if "/platform/login" not in self.driver.current_url:
                logger.info("Already logged in (redirected from login page)")
                return True
            
            logger.info("Looking for login elements...")
            
            # Find email input field - based on the HTML: input[type='email']
            try:
                email_input = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']"))
                )
            except TimeoutException:
                logger.error("Could not find email input field")
                self._save_debug_info("login_no_email")
                return False
            
            # Find password field
            password_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            
            # Enter credentials
            logger.info("Entering credentials...")
            email_input.clear()
            email_input.send_keys(self.email)
            time.sleep(0.3)
            
            password_input.clear()
            password_input.send_keys(self.password)
            time.sleep(0.3)
            
            # Find the "Sign in" button - it's a button[type='submit'] with class containing 'platform-auth-button'
            login_button = None
            
            # Try specific selector first
            try:
                login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            except:
                pass
            
            # Fallback: find button with "Sign in" text
            if not login_button:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    text = btn.text.lower().strip()
                    if 'sign in' in text or 'войти' in text or 'login' in text:
                        login_button = btn
                        break
            
            if login_button:
                logger.info(f"Clicking login button: '{login_button.text}'")
                # Use JavaScript click for reliability
                self.driver.execute_script("arguments[0].click();", login_button)
            else:
                # Fallback: submit form via Enter key
                logger.info("No button found, trying Enter key...")
                from selenium.webdriver.common.keys import Keys
                password_input.send_keys(Keys.RETURN)
            
            # Wait for redirect to lessons page
            logger.info("Waiting for login to complete...")
            try:
                # Wait for URL to change from login page
                WebDriverWait(self.driver, 15).until(
                    lambda d: "/platform/login" not in d.current_url
                )
                logger.info(f"Redirected to: {self.driver.current_url}")
            except TimeoutException:
                logger.warning("No redirect detected, checking page state...")
            
            # Give extra time for page to stabilize
            time.sleep(2)
            
            # Verify login by checking current URL
            current_url = self.driver.current_url
            logger.info(f"Current URL after login attempt: {current_url}")
            
            if "/platform/login" not in current_url:
                logger.info("Login successful! (redirected from login page)")
                return True
            
            # Still on login page - check for error messages
            error_elements = self.driver.find_elements(By.CSS_SELECTOR, "[class*='error'], [class*='alert'], .text-red-500")
            for elem in error_elements:
                if elem.text.strip():
                    logger.error(f"Login error message: {elem.text}")
            
            logger.error("Login failed - still on login page")
            self._save_debug_info("login_failed")
            return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            self._save_debug_info("login_error")
            return False

    
    def _is_logged_in(self) -> bool:
        """Check if user is logged in by looking for user elements."""
        try:
            # Look for elements that indicate logged-in state
            # Based on screenshot: user email in header, lesson content, etc.
            indicators = [
                ".user-info",
                ".user-email",
                "[class*='profile']",
                ".lesson-content",
                ".video-player"
            ]
            
            for selector in indicators:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    return True
            
            # Check URL - if we're on lessons page without redirect to login
            if "/platform/lessons" in self.driver.current_url:
                # Check for login form - if present, we're not logged in
                login_forms = self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
                if not login_forms:
                    return True
            
            return False
        except:
            return False
    
    def get_lessons(self) -> list[dict]:
        """
        Get all available lessons from the sidebar.
        
        Returns:
            List of lesson dictionaries with name, url, completed status
        """
        logger.info("Fetching lesson list...")
        lessons = []
        
        try:
            # Navigate to lessons page
            self.driver.get(self.LESSONS_URL)
            time.sleep(3)
            
            # Find lesson items in sidebar
            # Based on screenshot: lessons are in left sidebar with expandable sections
            lesson_selectors = [
                ".lesson-item",
                ".sidebar-item",
                "[class*='lesson']",
                ".menu-item"
            ]
            
            for selector in lesson_selectors:
                items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    for item in items:
                        try:
                            name = item.text.strip()
                            if name:
                                lessons.append({
                                    "name": name,
                                    "element": item,
                                    "completed": self._is_lesson_completed(item)
                                })
                        except:
                            continue
                    break
            
            logger.info(f"Found {len(lessons)} lessons")
            return lessons
            
        except Exception as e:
            logger.error(f"Error fetching lessons: {e}")
            return []
    
    def _is_lesson_completed(self, element) -> bool:
        """Check if a lesson is marked as completed."""
        try:
            # Look for completion indicators (checkmark, green color, etc.)
            classes = element.get_attribute("class") or ""
            if any(kw in classes.lower() for kw in ['completed', 'done', 'finished']):
                return True
            
            # Check for checkmark icon
            icons = element.find_elements(By.CSS_SELECTOR, "[class*='check'], [class*='done']")
            return len(icons) > 0
        except:
            return False
    
    def watch_video(self, timeout_seconds: int = 6000) -> bool:
        """
        Watch the current video until completion.
        
        Args:
            timeout_seconds: Maximum time to wait for video (auto-detected if None)
            
        Returns:
            True if video watched successfully
        """
        logger.info("Looking for video player...")
        
        try:
            # Find video element
            video_selectors = [
                "video",
                ".video-player video",
                "iframe[src*='youtube']",
                "iframe[src*='vimeo']",
                ".plyr video"
            ]
            
            video = None
            for selector in video_selectors:
                try:
                    video = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            
            if not video:
                logger.warning("No video found on page")
                return True  # Continue anyway
            
            # Try to play the video
            try:
                play_button = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    "[class*='play'], button[aria-label*='play' i], .plyr__control--play"
                )
                if play_button.is_displayed():
                    play_button.click()
                    logger.info("Clicked play button")
            except:
                # Try clicking the video directly
                try:
                    video.click()
                except:
                    pass
            
            # Get video duration and set timeout dynamically
            logger.info("Watching video...")
            # time.sleep(2)  # Wait for video metadata to load
            
            # # Auto-detect timeout based on video duration
            # if timeout_seconds is None:
            #     try:
            #         duration = self.driver.execute_script("return arguments[0].duration", video)
            #         if duration and duration > 0:
            #             # Add 60 second buffer for loading/delays
            #             timeout_seconds = int(duration) + 60
            #             logger.info(f"Video duration: {duration:.0f}s, timeout set to {timeout_seconds}s")
            #         else:
            #             timeout_seconds = 1800  # Default 30 minutes if can't detect
            #     except:
            #         timeout_seconds = 1800  # Default 30 minutes
            
            start_time = time.time()
            
            while time.time() - start_time < timeout_seconds:
                try:
                    # Check if video ended
                    ended = self.driver.execute_script(
                        "return arguments[0].ended || arguments[0].currentTime >= arguments[0].duration - 1",
                        video
                    )
                    if ended:
                        logger.info("Video completed!")
                        return True
                    
                    # Get current progress
                    current = self.driver.execute_script("return arguments[0].currentTime", video)
                    duration = self.driver.execute_script("return arguments[0].duration", video)
                    
                    if duration and duration > 0:
                        progress = (current / duration) * 100
                        logger.info(f"Video progress: {progress:.1f}% ({current:.0f}s / {duration:.0f}s)")
                    
                except Exception as e:
                    logger.debug(f"Could not get video progress: {e}")
                
                time.sleep(30)  # Check every 30 seconds
            
            logger.warning("Video timeout reached")
            return True
            
        except Exception as e:
            logger.error(f"Error watching video: {e}")
            return False
    
    def complete_test(self) -> bool:
        """
        Complete the test for the current lesson.
        
        Returns:
            True if test completed successfully
        """
        try:
            import re
            
            # First, check if test is already in progress (question visible on page)
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            test_already_open = False
            
            # Check for question pattern like "1.Calculate..." or "questions №"
            if re.search(r'\d+\.\s*[A-ZА-Яa-zа-я].{20,}', page_text) and 'questions' in page_text.lower():
                test_already_open = True
                logger.info("Test already in progress (question visible on page)")
            
            # Also check for "Time for the test" indicator
            if 'time for the test' in page_text.lower() or 'время на тест' in page_text.lower():
                test_already_open = True
                logger.info("Test already in progress (timer visible)")
            
            if not test_already_open:
                logger.info("Looking for test button...")
                
                # Find "Test task" / "Go to test" button
                test_button = None
                
                # Look for button/link with test-related text
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                buttons.extend(self.driver.find_elements(By.TAG_NAME, "a"))
                
                for btn in buttons:
                    try:
                        text = btn.text.lower()
                        if ('test' in text or 'тест' in text) and btn.is_displayed():
                            test_button = btn
                            break
                    except:
                        continue
                
                if not test_button:
                    logger.warning("No test button found")
                    return True  # Maybe no test for this lesson
                
                logger.info(f"Found test button: '{test_button.text}'")
                
                # Click the test button
                self.driver.execute_script("arguments[0].click();", test_button)
                
                # Wait for test page to load
                logger.info("Waiting for test page to load...")
                time.sleep(3)
                
                # Now look for "Start the test" button (NOT "Restart")
                logger.info("Looking for 'Start the test' button...")
                start_button = None
                restart_button = None  # Fallback
                
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    try:
                        text = btn.text.lower().strip()
                        if not btn.is_displayed():
                            continue
                        
                        # Prefer "start the test" over "restart"
                        if 'start the test' in text or 'начать тест' in text:
                            start_button = btn
                            break  # Found the exact button
                        elif 'start' in text and 'restart' not in text:
                            start_button = btn
                        elif 'restart' in text or 'перезапустить' in text:
                            restart_button = btn
                    except:
                        continue
                
                # Use start button, or fallback to restart
                button_to_click = start_button or restart_button
                
                if button_to_click:
                    logger.info(f"Found button: '{button_to_click.text}'")
                    self.driver.execute_script("arguments[0].click();", button_to_click)
                    logger.info("Clicked start/restart button")
                    
                    # Wait longer for questions to load
                    logger.info("Waiting for questions to load...")
                    time.sleep(5)
                else:
                    logger.warning("No 'Start the test' button found, trying to proceed anyway")
            
            # Wait for any loading indicators to disappear
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, "[class*='loading'], [class*='spinner']"))
                )
            except:
                pass
            
            # Save debug info to see what the test page looks like
            self._save_debug_info("test_questions")
            
            # Answer questions - tests always have 5 questions
            total_questions = 5
            answered_count = 0
            
            for question_num in range(1, total_questions + 1):
                logger.info(f"Attempting question {question_num} of {total_questions}")
                
                # Navigate to the question by clicking on the question number button
                # The test interface has numbered buttons (1, 2, 3, 4, 5) at the top
                self._navigate_to_question(question_num)
                time.sleep(1)
                
                if self._answer_current_question(expected_question_num=question_num):
                    answered_count += 1
                    logger.info(f"Successfully answered question {question_num}")
                else:
                    logger.warning(f"Failed to answer question {question_num}, continuing to next...")
                    # Try to click Next button anyway to move to next question
                    try:
                        next_button = None
                        buttons = self.driver.find_elements(By.TAG_NAME, "button")
                        for btn in buttons:
                            try:
                                text = btn.text.lower().strip()
                                if any(kw in text for kw in ['next', 'далее', 'следующий']):
                                    if btn.is_displayed() and btn.is_enabled():
                                        next_button = btn
                                        break
                            except:
                                continue
                        
                        if next_button:
                            logger.info(f"Clicking Next to skip to next question")
                            self.driver.execute_script("arguments[0].click();", next_button)
                            time.sleep(2)
                    except Exception as e:
                        logger.error(f"Could not click Next button: {e}")
                
                time.sleep(2)
            
            logger.info(f"Answered {answered_count} out of {total_questions} questions")
            
            # Look for submit/finish button after answering all questions
            if answered_count > 0:
                self._submit_test()
            
            return True
            
        except Exception as e:
            logger.error(f"Error completing test: {e}")
            self._save_debug_info("test_error")
            return False
    
    def _submit_test(self):
        """Submit/finish the test after answering all questions."""
        logger.info("Looking for submit button...")
        
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            try:
                text = btn.text.lower()
                if any(kw in text for kw in ['finish', 'submit', 'complete', 'завершить', 'отправить', 'end']):
                    if btn.is_displayed() and btn.is_enabled():
                        logger.info(f"Clicking submit button: '{btn.text}'")
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(2)
                        return
            except:
                continue
        
        logger.info("No submit button found")
    
    def _navigate_to_question(self, question_num: int):
        """Navigate to a specific question by clicking on the question number button."""
        try:
            # Look for question number buttons in the test interface
            # They're usually divs or buttons with just the number as text
            
            # Method 1: Look for elements with exact number text
            all_clickable = self.driver.find_elements(By.CSS_SELECTOR, "div.cursor-pointer, button")
            
            for elem in all_clickable:
                try:
                    text = elem.text.strip()
                    # Match exact number (but not longer numbers like "10" when looking for "1")
                    if text == str(question_num):
                        # Verify it's not a navigation button by checking parent context
                        parent_text = elem.find_element(By.XPATH, "..").text if elem else ""
                        # Question number buttons are usually near "questions №" or similar
                        if len(text) <= 2:  # Single or double digit
                            logger.info(f"Clicking question number button: {question_num}")
                            self.driver.execute_script("arguments[0].click();", elem)
                            time.sleep(1)
                            return
                except:
                    continue
            
            # Method 2: XPath for specific number in question selector area
            try:
                # Look for question numbers area (usually has "questions №" nearby)
                xpath = f"//div[contains(text(), 'questions')]/following-sibling::*//div[text()='{question_num}'] | //div[text()='{question_num}' and contains(@class, 'cursor-pointer')]"
                buttons = self.driver.find_elements(By.XPATH, xpath)
                for btn in buttons:
                    if btn.is_displayed():
                        logger.info(f"Clicking question number via XPath: {question_num}")
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1)
                        return
            except:
                pass
            
            logger.warning(f"Could not find question number button {question_num}")
            
        except Exception as e:
            logger.warning(f"Error navigating to question {question_num}: {e}")
    
    def _answer_current_question(self, expected_question_num: int = None) -> bool:
        """
        Answer the current question on screen.
        
        Args:
            expected_question_num: Expected question number (1-5) to verify we're on the right question
        
        Returns:
            True if question was answered AND there are more questions
        """
        try:
            # Narrow down the search scope to the main content area to avoid sidebar/header
            # The sidebar has class 'md:col-span-4'. The main content is likely the other sibling.
            search_context = self.driver.find_element(By.TAG_NAME, "body")
            
            try:
                # Try to find the main content grid
                main_grid = self.driver.find_element(By.CSS_SELECTOR, ".grid.grid-cols-12")
                # The sidebar is usually the first child or has 'md:col-span-4'
                # We want the content column, which might be 'md:col-span-8' or just the second large div
                children = main_grid.find_elements(By.XPATH, "./div")
                for child in children:
                    class_attr = child.get_attribute("class") or ""
                    # If it's NOT the sidebar (col-span-4), it's likely the content
                    if "col-span-4" not in class_attr:
                        search_context = child
                        logger.info("Found main content area")
                        break
            except:
                logger.warning("Could not identify main content area, searching whole body")
            
            # Look for any text that looks like a question (numbered, ending with ?)
            page_text = search_context.text
            
            # Try to find question text - look for numbered questions or text with ?
            question_text = None
            
            # First, try to find elements that look like questions
            # Questions may end with ? or . (some are "Calculate..." not "What is...?")
            import re
            all_elements = search_context.find_elements(By.CSS_SELECTOR, "p, div, span")
            for elem in all_elements:
                try:
                    text = elem.text.strip()
                    # Check if it looks like a question: starts with "N." and is long enough
                    if text and len(text) > 30 and re.match(r'^\d+\.', text):
                        # Avoid navigation elements
                        if not any(kw in text.lower() for kw in ['next', 'back', 'submit', 'start', 'finish', 'restart']):
                            question_text = text
                            logger.info(f"Found question element: {text[:80]}...")
                            break
                except:
                    continue  # Skip stale elements
            
            # Fallback: search for numbered text via regex in the page text
            if not question_text:
                # Allow optional space after dot: "1.What" or "1. What"
                # Question may end with ? or . (some questions are "Calculate..." not "What is...?")
                question_match = re.search(r'\d+\.\s*[A-ZА-Яa-zа-я].{20,}[\?\.]', page_text)
                if question_match:
                    question_text = question_match.group(0)
                    logger.info(f"Found question via regex: {question_text[:80]}...")
            
            if not question_text:
                # Log what we see on the page for debugging
                logger.info("No question text found. Content text preview:")
                logger.info(page_text[:500] if len(page_text) > 500 else page_text)
                return False
            
            # Log if we're on a different question than expected (but don't fail)
            if expected_question_num is not None:
                found_num_match = re.match(r'^(\d+)\.', question_text)
                if found_num_match:
                    found_question_num = int(found_num_match.group(1))
                    if found_question_num != expected_question_num:
                        logger.warning(f"Expected question {expected_question_num}, but found question {found_question_num}. Answering anyway.")
                        # Don't return False - try to answer the visible question
            
            logger.info(f"Question: {question_text[:100]}...")
            
            # Find answer options - look for radio/checkbox inputs or clickable divs with option text
            options = []
            option_elements = []
            
            # Method 1: Look for inputs (radio/checkbox) - best method
            radio_inputs = search_context.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
            
            if radio_inputs:
                logger.info(f"Found {len(radio_inputs)} radio/checkbox inputs")
                for radio in radio_inputs:
                    try:
                        # Find the label or parent element containing the text
                        # Usually the text is in a sibling or parent
                        parent = radio.find_element(By.XPATH, "./..")
                        text = parent.text.strip()
                        if text:
                            options.append(text)
                            option_elements.append(parent)
                        else:
                            # Try label associated with id
                            radio_id = radio.get_attribute("id")
                            if radio_id:
                                try:
                                    label = search_context.find_element(By.CSS_SELECTOR, f"label[for='{radio_id}']")
                                    text = label.text.strip()
                                    if text:
                                        options.append(text)
                                        option_elements.append(label)
                                except:
                                    pass
                    except:
                        continue
            
            # Method 2: Look for clickable option divs with cursor-pointer class
            # This is the primary method for this website
            if not options:
                logger.info("No radio inputs found, looking for clickable div options")
                # Look for divs with cursor-pointer class that have option-like structure
                # Based on HTML: div.cursor-pointer containing a p tag with the option text
                potential_options = search_context.find_elements(
                    By.CSS_SELECTOR, 
                    "div.cursor-pointer"
                )
                
                logger.info(f"Found {len(potential_options)} cursor-pointer divs")
                
                for div in potential_options:
                    try:
                        text = div.text.strip()
                        class_attr = div.get_attribute('class') or ''
                        
                        # Check if this looks like an option container
                        # Answer options typically have bg-gray-cool class OR rounded+padding styles
                        is_answer_option = (
                            'bg-gray-cool' in class_attr or  # Primary answer option indicator
                            ('rounded' in class_attr and 'px-' in class_attr)  # Alternative style
                        )
                        
                        # Check if it's a pure question number like "1." or "2." (not an answer)
                        is_question_number = (
                            len(text) <= 3 and 
                            text[0].isdigit() and 
                            (text.endswith('.') or text.isdigit())
                        )
                        
                        if (text and 
                            1 < len(text) < 150 and  # Allow short numeric answers like "0.5"
                            '\n' not in text and  # Single line
                            not is_question_number and  # Not a question number like "1."
                            is_answer_option):
                            
                            # Filter out navigation/control elements
                            if not any(kw in text.lower() for kw in [
                                'next', 'back', 'submit', 'start', 'finish', 
                                'restart', 'question', 'timer', 'deadline',
                                'ответьте на все', 'answer all'
                            ]):
                                if text not in options:
                                    options.append(text)
                                    option_elements.append(div)
                                    logger.debug(f"Found option: {text[:50]}...")
                    except:
                        continue
            
            # Method 3: Fallback - look for any divs that might be options
            if not options:
                logger.info("Trying fallback method for option detection")
                all_divs = search_context.find_elements(By.CSS_SELECTOR, "div")
                for div in all_divs:
                    try:
                        text = div.text.strip()
                        class_attr = div.get_attribute('class') or ''
                        
                        # Check if it's a pure question number like "1." or "2."
                        is_question_number = (
                            len(text) <= 3 and 
                            text[0].isdigit() and 
                            (text.endswith('.') or text.isdigit())
                        )
                        
                        # Options can be various lengths, allow numbers at start (math answers)
                        # Allow short numeric answers like "0.5", "0.7854"
                        if text and 1 < len(text) < 100 and '\n' not in text:
                            if not is_question_number:
                                if not any(kw in text.lower() for kw in [
                                    'next', 'back', 'submit', 'start', 'finish', 
                                    'question', 'time', 'ответьте на все', 'answer all'
                                ]):
                                    # Check visual cues - look for clickable/option-like elements
                                    is_clickable = (
                                        'cursor' in class_attr or 
                                        'rounded' in class_attr or
                                        'bg-gray-cool' in class_attr or
                                        'text-unix' in class_attr
                                    )
                                    if is_clickable:
                                        if text not in options:
                                            options.append(text)
                                            option_elements.append(div)
                    except:
                        continue
            
            if not options:
                logger.warning("No answer options found using any method")
                return False
            
            # Filter and deduplicate
            unique_options = []
            unique_elements = []
            for i, opt in enumerate(options):
                # Simple cleanup
                opt = opt.strip() 
                if opt and opt not in unique_options and len(unique_options) < 6:
                    unique_options.append(opt)
                    unique_elements.append(option_elements[i])
            
            options = unique_options
            option_elements = unique_elements
            logger.info(f"Found {len(options)} unique options: {options}")
            
            # Use AI to get the answer
            if self.ai_helper:
                answer_idx = self.ai_helper.answer_question(question_text, options)
            else:
                logger.warning("AI not available, selecting first option")
                answer_idx = 0
            
            # Save question and answers to database BEFORE clicking
            if self.db_manager and answer_idx < len(options):
                try:
                    success = self.db_manager.save_question_with_answers(
                        user_email=self.email,
                        question_text=question_text,
                        answer_options=options,
                        selected_answer_idx=answer_idx,
                        lesson_name=self.current_lesson_name,
                        lesson_url=self.current_lesson_url
                    )
                    if success:
                        logger.info("Question and answers saved to database")
                    else:
                        logger.warning("Failed to save question to database")
                except Exception as e:
                    logger.error(f"Error saving to database: {e}")
            
            # Click the answer - re-find element to avoid stale reference
            if answer_idx < len(options):
                selected_option_text = options[answer_idx]
                logger.info(f"Selecting answer {answer_idx + 1}: {selected_option_text[:50]}...")
                
                # Re-find the option element to avoid stale reference issues
                # The page may have re-rendered since we first found the elements
                option = None
                
                # Try to find the element containing this exact text
                try:
                    # Find all cursor-pointer divs again
                    potential_options = search_context.find_elements(By.CSS_SELECTOR, "div.cursor-pointer")
                    logger.info(f"Re-searching: found {len(potential_options)} cursor-pointer divs")
                    
                    for div in potential_options:
                        try:
                            div_text = div.text.strip()
                            logger.info(f"Comparing option text: '{div_text}' vs '{selected_option_text}'")
                            if div_text == selected_option_text:
                                option = div
                                logger.info(f"Re-found option element for: {selected_option_text[:30]}...")
                                break
                        except Exception as inner_e:
                            logger.warning(f"Error getting text from div: {inner_e}")
                            continue
                    
                    # Fallback: use xpath to find element by text
                    if not option:
                        logger.info("Trying XPath to find option by text")
                        # Look for any element containing this exact text
                        xpath = f"//div[contains(@class, 'cursor-pointer') and normalize-space(.)='{selected_option_text}']"
                        try:
                            option = search_context.find_element(By.XPATH, xpath)
                            logger.info("Found using XPath exact match")
                        except:
                            # Try partial match if exact doesn't work
                            xpath = f"//div[contains(@class, 'cursor-pointer') and contains(normalize-space(.), '{selected_option_text[:30]}')]"
                            option = search_context.find_element(By.XPATH, xpath)
                            logger.info("Found using XPath partial match")
                
                except Exception as e:
                    logger.error(f"Could not re-find option element: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return False
                
                if not option:
                    logger.error(f"Could not find option with text: {selected_option_text}")
                    return False
                
                # Give the element a moment to become fully interactive
                time.sleep(0.5)
                
                # Scroll element into view
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", option)
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Could not scroll to element: {e}")
                
                # Try multiple click strategies
                clicked = False
                
                # Strategy 1: Direct click
                try:
                    option.click()
                    clicked = True
                    logger.info("Clicked using direct click")
                except Exception as e:
                    logger.debug(f"Direct click failed: {e}")
                
                # Strategy 2: JavaScript click
                if not clicked:
                    try:
                        self.driver.execute_script("arguments[0].click();", option)
                        clicked = True
                        logger.info("Clicked using JavaScript")
                    except Exception as e:
                        logger.debug(f"JavaScript click failed: {e}")
                
                # Strategy 3: Click the inner radio button circle if it exists
                if not clicked:
                    try:
                        # Look for the visual radio button (the circular div)
                        inner_circle = option.find_element(By.CSS_SELECTOR, "div[class*='rounded-full']")
                        self.driver.execute_script("arguments[0].click();", inner_circle)
                        clicked = True
                        logger.info("Clicked using inner circle")
                    except Exception as e:
                        logger.debug(f"Inner circle click failed: {e}")
                
                # Strategy 4: Try ActionChains
                if not clicked:
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(option).click().perform()
                        clicked = True
                        logger.info("Clicked using ActionChains")
                    except Exception as e:
                        logger.debug(f"ActionChains click failed: {e}")
                
                # Strategy 5: Try clicking the p tag with the text
                if not clicked:
                    try:
                        p_tag = option.find_element(By.TAG_NAME, "p")
                        self.driver.execute_script("arguments[0].click();", p_tag)
                        clicked = True
                        logger.info("Clicked p tag")
                    except Exception as e:
                        logger.debug(f"P tag click failed: {e}")
                
                if not clicked:
                    logger.error("Failed to click option using any strategy - will retry")
                    # Try one more time with a longer wait
                    time.sleep(1)
                    try:
                        # Try refreshing the element reference one more time
                        potential_options = search_context.find_elements(By.CSS_SELECTOR, "div.cursor-pointer")
                        for div in potential_options:
                            if div.text.strip() == selected_option_text:
                                self.driver.execute_script("arguments[0].click();", div)
                                clicked = True
                                logger.info("Retry click succeeded!")
                                break
                    except Exception as e:
                        logger.error(f"Retry also failed: {e}")
                    
                    if not clicked:
                        logger.error("All click attempts failed, skipping this question")
                        return False
                
                time.sleep(1)
                
                # Look for "Next" button within the search context
                next_button = None
                buttons = search_context.find_elements(By.TAG_NAME, "button")
                
                for btn in buttons:
                    try:
                        text = btn.text.lower().strip()
                        if any(kw in text for kw in ['next', 'далее', 'следующий']):
                            if btn.is_displayed() and btn.is_enabled():
                                next_button = btn
                                break
                    except:
                        continue
                
                if next_button:
                    logger.info(f"Clicking: {next_button.text}")
                    self.driver.execute_script("arguments[0].click();", next_button)
                    # Wait longer for page to update
                    time.sleep(3)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            return False
    
    def process_lesson(self, lesson_name: str) -> bool:
        """
        Process a single lesson: watch video and complete test.
        
        Args:
            lesson_name: Name of the lesson to process
            
        Returns:
            True if lesson processed successfully
        """
        logger.info(f"Processing lesson: {lesson_name}")
        self.current_lesson_name = lesson_name
        self.current_lesson_url = self.driver.current_url  # Initial URL
        
        # Click on the lesson
        try:
            lessons = self.get_lessons()
            target_lesson = None
            
            for lesson in lessons:
                if lesson_name.lower() in lesson["name"].lower():
                    target_lesson = lesson
                    break
            
            if target_lesson:
                self.driver.execute_script("arguments[0].click();", target_lesson["element"])
                time.sleep(3)
                self.current_lesson_url = self.driver.current_url  # Update URL after navigation
        except:
            pass
        
        # Watch video
        self.watch_video()
        
        # Complete test
        self.complete_test()
        
        return True
    
    def run(self):
        """Main execution loop - process all lessons."""
        logger.info("Starting UniX Agent...")
        
        try:
            self.setup_driver()
            self.setup_ai()
            self.setup_database()
            
            if not self.login():
                logger.error("Failed to login. Exiting.")
                return
            
            # Get all lessons
            lessons = self.get_lessons()
            
            if not lessons:
                logger.warning("No lessons found")
                return
            
            # Process each uncompleted lesson
            for lesson in lessons:
                if not lesson.get("completed", False):
                    self.process_lesson(lesson["name"])
                    time.sleep(5)  # Pause between lessons
            
            logger.info("All lessons processed!")
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")
    
    def _save_debug_info(self, prefix: str):
        """Save debug information for troubleshooting."""
        try:
            timestamp = int(time.time())
            
            # Save screenshot
            screenshot_path = f"images/debug_{prefix}_{timestamp}.png"
            self.driver.save_screenshot(screenshot_path)
            logger.info(f"Saved screenshot: {screenshot_path}")
            
            # Save page source
            html_path = f"images/debug_{prefix}_{timestamp}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.info(f"Saved page source: {html_path}")
            
        except Exception as e:
            logger.error(f"Failed to save debug info: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="UniX Platform Lecture Agent")
    parser.add_argument("--test-login", action="store_true", help="Test login only")
    parser.add_argument("--test-navigation", action="store_true", help="Test lesson navigation")
    parser.add_argument("--test-ai", action="store_true", help="Test AI helper")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--lesson", type=str, help="Specific lesson URL to process (e.g., https://uni-x.almv.kz/platform/lessons/9839)")
    parser.add_argument("--skip-video", action="store_true", help="Skip video watching and go directly to test (use if video already watched)")
    parser.add_argument("--batch", action="store_true", help="Process multiple lessons in sequence")
    parser.add_argument("--start-id", type=int, help="Starting lesson ID for batch mode")
    parser.add_argument("--end-id", type=int, help="Ending lesson ID for batch mode (optional, will continue until lesson not found)")
    parser.add_argument("--max-lessons", type=int, default=50, help="Maximum number of lessons to process in batch mode (default: 50)")
    args = parser.parse_args()
    
    load_dotenv()
    
    email = os.getenv("UNIX_EMAIL")
    password = os.getenv("UNIX_PASSWORD")
    
    if not email or not password:
        logger.error("UNIX_EMAIL and UNIX_PASSWORD must be set in .env file")
        return
    
    agent = UniXAgent(email, password, headless=args.headless)
    
    if args.test_ai:
        from ai_helper import test_ai_helper
        test_ai_helper()
        return
    
    if args.test_login:
        agent.setup_driver()
        try:
            success = agent.login()
            print(f"Login {'successful' if success else 'failed'}")
        finally:
            agent.cleanup()
        return
    
    if args.test_navigation:
        agent.setup_driver()
        agent.setup_ai()
        try:
            if agent.login():
                lessons = agent.get_lessons()
                for i, lesson in enumerate(lessons):
                    print(f"{i+1}. {lesson['name']} - {'✓' if lesson['completed'] else '○'}")
        finally:
            agent.cleanup()
        return
    
    # Batch mode - process multiple lessons in sequence
    if args.batch:
        if not args.start_id:
            logger.error("--start-id is required for batch mode")
            return
        
        agent.setup_driver()
        agent.setup_ai()
        agent.setup_database()
        
        try:
            if not agent.login():
                logger.error("Login failed, cannot process lessons")
                return
            
            current_id = args.start_id
            end_id = args.end_id if args.end_id else (args.start_id + args.max_lessons)
            lessons_processed = 0
            lessons_failed = 0
            consecutive_failures = 0
            max_consecutive_failures = 3  # Stop after 3 consecutive failures (likely reached end)
            
            logger.info(f"=== BATCH MODE: Starting from lesson {current_id} ===")
            if args.end_id:
                logger.info(f"Will process until lesson {end_id}")
            else:
                logger.info(f"Will process up to {args.max_lessons} lessons or until not found")
            
            while current_id <= end_id and lessons_processed < args.max_lessons:
                lesson_url = f"https://uni-x.almv.kz/platform/lessons/{current_id}"
                logger.info(f"\n{'='*50}")
                logger.info(f"Processing lesson {current_id} ({lessons_processed + 1}/{args.max_lessons})")
                logger.info(f"{'='*50}")
                
                try:
                    # Navigate to lesson
                    agent.driver.get(lesson_url)
                    time.sleep(3)
                    
                    # Check if lesson exists (look for error page or redirect)
                    current_url = agent.driver.current_url
                    page_source = agent.driver.page_source.lower()
                    
                    # Check for signs that lesson doesn't exist
                    if (
                        "404" in page_source or 
                        "not found" in page_source or
                        "error" in agent.driver.title.lower() or
                        "/platform/lessons/" not in current_url
                    ):
                        logger.warning(f"Lesson {current_id} not found or not accessible, skipping...")
                        consecutive_failures += 1
                        if consecutive_failures >= max_consecutive_failures:
                            logger.info(f"Reached {max_consecutive_failures} consecutive failures, likely at the end of available lessons")
                            break
                        current_id += 1
                        continue
                    
                    # Reset consecutive failures on success
                    consecutive_failures = 0
                    
                    # Update current lesson info
                    agent.current_lesson_url = lesson_url
                    agent.current_lesson_name = f"Lesson {current_id}"
                    
                    # Try to get lesson title from page
                    try:
                        title_elem = agent.driver.find_element(By.CSS_SELECTOR, "h1, .lesson-title, [class*='title']")
                        if title_elem:
                            agent.current_lesson_name = title_elem.text.strip()[:100]
                    except:
                        pass
                    
                    # Watch video (unless skipped)
                    if args.skip_video:
                        logger.info("Skipping video (--skip-video flag set)")
                    else:
                        logger.info("Watching video...")
                        agent.watch_video()
                    
                    # Complete test
                    logger.info("Starting test...")
                    agent.complete_test()
                    
                    lessons_processed += 1
                    logger.info(f"Lesson {current_id} completed successfully!")
                    
                except Exception as e:
                    logger.error(f"Error processing lesson {current_id}: {e}")
                    lessons_failed += 1
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.info(f"Reached {max_consecutive_failures} consecutive failures, stopping batch")
                        break
                
                # Move to next lesson
                current_id += 1
                
                # Small delay between lessons
                if current_id <= end_id:
                    logger.info("Waiting before next lesson...")
                    time.sleep(2)
            
            logger.info(f"\n{'='*50}")
            logger.info(f"BATCH COMPLETE")
            logger.info(f"Lessons processed: {lessons_processed}")
            logger.info(f"Lessons failed: {lessons_failed}")
            logger.info(f"{'='*50}")
            
        except KeyboardInterrupt:
            logger.info("\nBatch interrupted by user")
        except Exception as e:
            logger.exception(f"Batch error: {e}")
        finally:
            agent.cleanup()
        return
    
    # Process specific lesson
    if args.lesson:
        agent.setup_driver()
        agent.setup_ai()
        agent.setup_database()
        try:
            if agent.login():
                logger.info(f"Navigating to lesson: {args.lesson}")
                agent.driver.get(args.lesson)
                time.sleep(3)
                
                # Update lesson info
                agent.current_lesson_url = args.lesson
                
                # Watch video (unless skipped)
                if args.skip_video:
                    logger.info("Skipping video (--skip-video flag set)")
                else:
                    agent.watch_video()
                
                # Complete test
                agent.complete_test()
                
                logger.info("Lesson processing complete!")
            else:
                logger.error("Login failed, cannot process lesson")
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.exception(f"Error: {e}")
        finally:
            agent.cleanup()
        return
    
    # Run full agent
    agent.run()


if __name__ == "__main__":
    main()

