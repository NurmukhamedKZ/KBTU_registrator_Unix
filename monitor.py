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
        # Wait longer for Vaadin to load
        wait = WebDriverWait(driver, 30)
        
        logging.info("Checking for login inputs or login button...")
        
        # Check for inputs OR login button
        # XPath to find login button by icon src
        login_btn_xpath = "//img[contains(@src, 'login_24.png')]/ancestor::div[contains(@class, 'v-button')]"
        
        try:
            # Wait for either input or login button
            wait.until(lambda d: d.find_elements(By.TAG_NAME, "input") or d.find_elements(By.XPATH, login_btn_xpath))
        except TimeoutException:
             # Just proceed to failure logic if nothing found
             pass
        
        # If no inputs, check for login button and click it
        inputs = driver.find_elements(By.TAG_NAME, "input")
        if not inputs:
            logging.info("No inputs found, looking for login button...")
            login_btns = driver.find_elements(By.XPATH, login_btn_xpath)
            if login_btns:
                logging.info("Found login button, clicking via JS...")
                driver.execute_script("arguments[0].click();", login_btns[0])
                # Now wait for inputs
                logging.info("Waiting for inputs to appear after click...")
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
                inputs = driver.find_elements(By.TAG_NAME, "input")
            else:
                 logging.warning("No inputs and no login button found.")
        
        logging.info(f"Found {len(inputs)} input fields.")
        
        user_input = None
        pass_input = None
        
        # Heuristic to identify fields
        for inp in inputs:
            type_attr = inp.get_attribute("type")
            if type_attr == "text" and not user_input:
                user_input = inp
            elif type_attr == "password":
                pass_input = inp
        
        if not user_input or not pass_input:
            # Fallback for Vaadin specific structure if needed or if username is not 'text'
            # Sometimes username is the first visible input
             logging.warning("Could not clearly identify user/pass inputs. Dumping page source.")
             html_path = "images/debug_page_source.html"
             with open(html_path, "w", encoding="utf-8") as f:
                 f.write(driver.page_source)
             raise NoSuchElementException("Username or Password field not identified uniquely.")

        logging.info("Entering credentials...")
        user_input.clear()
        user_input.send_keys(username)
        pass_input.clear()
        pass_input.send_keys(password)
        
        # Look for login button - generic approach
        # Vaadin buttons often are divs with role button or specific classes
        # After entering creds, the button might be different.
        # Often it's another button "Войти" or similar.
        
        # Ensure values are committed (Vaadin sometimes needs blur)
        from selenium.webdriver.common.keys import Keys
        if pass_input:
            pass_input.send_keys(Keys.TAB)
        
        # Let's re-scan for buttons since the DOM might have changed or overlay opened
        buttons = driver.find_elements(By.XPATH, "//div[contains(@class, 'v-button')] | //button | //input[@type='submit']")
        
        clicked = False
        
        # First priority: Primary buttons
        primary_buttons = driver.find_elements(By.XPATH, "//div[contains(@class, 'v-button-primary')]")
        if primary_buttons:
             logging.info("Found primary login button, clicking via JS...")
             driver.execute_script("arguments[0].click();", primary_buttons[0])
             clicked = True
        
        if not clicked:
            for btn in buttons:
                if btn.is_displayed():
                    # Prefer buttons with text like "Login" "Войти" etc
                    txt = btn.text.lower()
                    # Also check for "success" icon or new login button
                    if any(k in txt for k in ['login', 'enter', 'вход', 'войти', 'кіру']) or not txt:
                        # Avoid clicking the specific "Key" login button we just clicked if it's still there
                        # But usually a modal appears.
                        logging.info(f"Clicking potential submit button '{txt}' via JS...")
                        driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        break
        
        if not clicked and buttons:
            # Be careful not to click 'Cancel' or X
            # Vaadin modals usually have [Login] [Cancel]
            # We hope the first one or primary one is Login
            logging.info("Clicking first available button via JS...")
            driver.execute_script("arguments[0].click();", buttons[0])
        
        # Wait for redirect or check for successful login element
        time.sleep(5) # Simple wait for transition
        
        # Verification Step
        logging.info("Verifying login by navigating to /Stud...")
        driver.get("https://wsp.kbtu.kz/Stud")
        time.sleep(5)
        
        current_url = driver.current_url
        page_source = driver.page_source
        
        # Check if we are still on login page or have access
        # Heuristic: If we see "Login" or "Вход" inputs again, we failed.
        # If we see student info or specific text, we succeeded.
        if "LoginView" in current_url or len(driver.find_elements(By.XPATH, "//input[@type='password']")) > 0:
             logging.error("Login verification failed. Still finding login elements on /Stud page.")
             raise Exception("Login failed - redirected to login page.")
        
        logging.info("Login verified successfully (No login fields found on /Stud).")
        
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
