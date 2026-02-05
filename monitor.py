import os
import time
import logging
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException




# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)

def setup_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless") # Comment out to see the browser
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Automatically install/manage Chrome driver
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    return driver

def login(driver, username, password):
    logging.info("Navigating to login page...")
    driver.get("https://wsp.kbtu.kz/")
    
    try:
        wait = WebDriverWait(driver, 30)
        from selenium.webdriver.common.keys import Keys
        
        # Wait for the page to load
        logging.info("Waiting for page to load...")
        time.sleep(3)
        
        # Step 1: Click the login button (key icon) to open the login modal
        logging.info("Looking for login button (key icon)...")
        login_btn_xpath = "//img[contains(@src, 'login_24.png')]/ancestor::div[contains(@class, 'v-button')]"
        
        login_btns = driver.find_elements(By.XPATH, login_btn_xpath)
        if login_btns:
            logging.info("Found login button, clicking to open login form...")
            driver.execute_script("arguments[0].click();", login_btns[0])
            time.sleep(2)  # Wait for modal to appear
        else:
            logging.warning("Login button not found, form might already be visible")
        
        # Step 2: Wait for the login form to appear
        logging.info("Waiting for login form to appear...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        time.sleep(1)
        
        # Find username field - could be text input or combobox
        logging.info("Looking for username field...")
        user_input = None
        
        # Try various selectors for username
        username_selectors = [
            "input[type='text']",
            ".v-filterselect input",
            ".v-textfield"
        ]
        
        for selector in username_selectors:
            inputs = driver.find_elements(By.CSS_SELECTOR, selector)
            for inp in inputs:
                if inp.is_displayed():
                    user_input = inp
                    logging.info(f"Found username input with selector: {selector}")
                    break
            if user_input:
                break
        
        # Find password field
        logging.info("Looking for password field...")
        pass_input = None
        password_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        for inp in password_inputs:
            if inp.is_displayed():
                pass_input = inp
                logging.info("Found password input field")
                break
        
        if not pass_input:
            logging.error("Password field not found!")
            raise NoSuchElementException("Password field not found")
        
        # Enter username
        if user_input:
            logging.info(f"Entering username: {username}")
            # Click to focus, then use JS to set value
            user_input.click()
            time.sleep(0.3)
            user_input.clear()
            user_input.send_keys(username)
            time.sleep(0.5)
            # Press Tab to confirm and move to password
            user_input.send_keys(Keys.TAB)
            time.sleep(0.5)
        else:
            logging.warning("Username input not found!")
        
        # Re-find password field (DOM might have changed)
        logging.info("Re-finding password field...")
        pass_input = None
        password_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        for inp in password_inputs:
            if inp.is_displayed():
                pass_input = inp
                break
        
        if not pass_input:
            raise NoSuchElementException("Password field not found after username entry")
        
        # Enter password using multiple methods
        logging.info("Entering password...")
        pass_input.click()
        time.sleep(0.3)
        
        # Method 1: Direct send_keys
        pass_input.clear()
        pass_input.send_keys(password)
        time.sleep(0.3)
        
        # Verify password was entered
        entered_pass = pass_input.get_attribute("value")
        logging.info(f"Password field value length: {len(entered_pass) if entered_pass else 0}")
        
        # If password is empty, try JS method
        if not entered_pass:
            logging.warning("Password not entered via send_keys, trying JavaScript...")
            driver.execute_script("""
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            """, pass_input, password)
            time.sleep(0.3)
        
        time.sleep(0.5)
        
        # Find and click the login button "Кіру"
        logging.info("Looking for login button (Кіру)...")
        login_button = None
        
        # Try multiple selectors
        button_selectors = [
            "//button[contains(text(), 'Кіру')]",
            "//div[contains(@class, 'v-button')][contains(., 'Кіру')]",
            "//span[contains(text(), 'Кіру')]/ancestor::button",
            "//span[contains(text(), 'Кіру')]/ancestor::div[contains(@class, 'v-button')]",
            "//button[contains(@class, 'primary')]",
            "//div[contains(@class, 'v-button-primary')]"
        ]
        
        for selector in button_selectors:
            buttons = driver.find_elements(By.XPATH, selector)
            for btn in buttons:
                if btn.is_displayed():
                    login_button = btn
                    logging.info(f"Found login button with selector: {selector}")
                    break
            if login_button:
                break
        
        # Fallback: find any button with "Кіру" or "Войти" text
        if not login_button:
            all_buttons = driver.find_elements(By.CSS_SELECTOR, "button, .v-button, [role='button']")
            for btn in all_buttons:
                text = btn.text.lower()
                if any(kw in text for kw in ['кіру', 'войти', 'login', 'enter', 'вход']):
                    if btn.is_displayed():
                        login_button = btn
                        logging.info(f"Found login button by text: {btn.text}")
                        break
        
        if login_button:
            logging.info("Clicking login button...")
            driver.execute_script("arguments[0].click();", login_button)
        else:
            # Try pressing Enter on password field
            logging.warning("Login button not found, pressing Enter...")
            pass_input.send_keys(Keys.RETURN)
        
        # Wait for login to complete
        logging.info("Waiting for login response...")
        time.sleep(3)
        
        # Take screenshot right after login attempt to see any error message
        try:
            driver.save_screenshot("images/debug_after_login_click.png")
            logging.info("Saved screenshot after login click")
        except:
            pass
        
        # Check for error messages
        error_selectors = [
            ".v-Notification",
            ".v-errorindicator",
            "[class*='error']",
            "[class*='notification']"
        ]
        for sel in error_selectors:
            errors = driver.find_elements(By.CSS_SELECTOR, sel)
            for err in errors:
                if err.is_displayed() and err.text:
                    logging.error(f"Found error message: {err.text}")
        
        time.sleep(2)
        
        # Verification Step
        logging.info("Verifying login by navigating to /Stud...")
        driver.get("https://wsp.kbtu.kz/Stud")
        time.sleep(5)
        
        current_url = driver.current_url
        
        # Check if we are still on login page or have access
        password_fields = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        visible_password_fields = [f for f in password_fields if f.is_displayed()]
        
        if visible_password_fields:
            logging.error("Login verification failed. Still finding login elements on /Stud page.")
            raise Exception("Login failed - redirected to login page.")
        
        logging.info("Login verified successfully!")
        
    except Exception as e:
        logging.error(f"Login failed: {e}")
        logging.info(f"Current URL: {driver.current_url}")
        logging.info(f"Page Title: {driver.title}")
        
        try:
            html_path = "images/debug_page_source.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logging.info(f"Saved {html_path}")
            
            screenshot_path = "images/debug_screenshot.png"
            driver.save_screenshot(screenshot_path)
            logging.info(f"Saved {screenshot_path}")
        except Exception as dump_e:
            logging.error(f"Failed to save debug info: {dump_e}")
            
        raise

def monitor_registration(driver):
    target_url = "https://wsp.kbtu.kz/RegistrationOnline"
    logging.info(f"Navigating to {target_url}...")
    driver.get(target_url)
    
    logging.info("Starting monitoring loop. Press Ctrl+C to stop.")
    
    while True:
        try:
            # We look for a button that might indicate registration is open
            # Strategies: Text match, Class match
            # Keywords: "Register", "Confirm", "Подтвердить", "Регистрация"
            
            # Simple check logic:
            # 1. Refresh page? Or is it dynamic? Usually these systems require refresh or poll.
            # Let's assume refresh for now to be safe, or just check if element appears if using AJAX.
            # If the user says "button appears", it might be dynamic, but WSP is old, so likely refresh needed or it's a simple hidden element.
            
            driver.refresh()
            time.sleep(2) # Wait for load
            
            buttons = driver.find_elements(By.TAG_NAME, "button")
            found = False
            for btn in buttons:
                text = btn.text.lower()
                if any(kw in text for kw in ["confirm", "подтвердить", "register", "регистрация", "save", "сохранить"]):
                    logging.info(f"Found candidate button: '{btn.text}'. Clicking...")
                    btn.click()
                    found = True
                    logging.info("Clicked button!")
                    time.sleep(5) # Wait to see result
                    break
            
            # Fallback for inputs of type button/submit
            if not found:
                inputs = driver.find_elements(By.TAG_NAME, "input")
                for inp in inputs:
                    if inp.get_attribute("type") in ["button", "submit"]:
                        val = inp.get_attribute("value").lower()
                        if any(kw in val for kw in ["confirm", "подтвердить", "register", "регистрация"]):
                             logging.info(f"Found candidate input button: '{inp.get_attribute('value')}'. Clicking...")
                             inp.click()
                             found = True
                             time.sleep(5)
                             break
            
            if not found:
                logging.info("No registration button found. Retrying in 60 seconds...")
            
            time.sleep(60)
            
        except Exception as e:
            logging.error(f"Error during monitoring: {e}")
            time.sleep(60) # Wait before retry on error

def main():
    load_dotenv()
    username = os.getenv("KBTU_USERNAME")
    password = os.getenv("KBTU_PASSWORD")
    
    if not username or not password:
        logging.error("Credentials not found in .env file. Please create one.")
        return

    driver = None
    try:
        driver = setup_driver()
        login(driver, username, password)
        monitor_registration(driver)
    except KeyboardInterrupt:
        logging.info("Stopping script...")
    except Exception as e:
        logging.exception("An unexpected error occurred:")
    finally:
        if driver:
            driver.quit()
            logging.info("Driver closed.")

if __name__ == "__main__":
    main()
