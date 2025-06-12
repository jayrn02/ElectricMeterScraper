from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
import json
import time
import os
from mqtt_publisher import publish_imagine_json
from datetime import datetime, timezone, timedelta
from excel_exporter import export_imagine_data

def load_credentials(file_path=None, service="Imagine"):
    if file_path is None:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "credentials.json")
    try:
        with open(file_path, 'r') as f:
            creds = json.load(f)
            # Check if the service exists in the credentials
            if service not in creds:
                print(f"Error: Service '{service}' not found in '{file_path}'.")
                return None, None
            
            service_creds = creds[service]
            # Return serviceNumber and accountNumber for Imagine
            if service == "Imagine":
                return service_creds.get("serviceNumber"), service_creds.get("accountNumber")
            else:
                print(f"Error: Unknown service '{service}'.")
                return None, None
    except FileNotFoundError:
        print(f"Error: Credentials file '{file_path}' not found.")
        return None, None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{file_path}'.")
        return None, None
    except KeyError as e:
        print(f"Error: Required key not found in '{file_path}': {e}")
        return None, None

def scrape_usage_data(driver):
    usage_data = {}
    
    try:
        # Wait for the page to load after form submission
        print("Waiting for usage data to load...")
        time.sleep(5)
        
        # Wait for the specific div container to be present
        print("Looking for usage data container...")
        usage_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "divBar"))
        )
        print("Usage container found!")
        
        # Look for progress bars with usage data
        progress_bars = usage_container.find_elements(By.CSS_SELECTOR, ".progress-bar span")
        
        for i, span in enumerate(progress_bars):
            span_text = span.text.strip()
            if span_text:
                if "GB Used" in span_text:
                    if i == 0:  # First progress bar is Base Plan
                        usage_data["Base Plan Usage"] = span_text
                        print(f"Base Plan Usage: {span_text}")
                    elif i == 1:  # Second progress bar is Topup
                        usage_data["Topup Usage"] = span_text
                        print(f"Topup Usage: {span_text}")
        
        # Also look for the total allowances and expiry information
        try:
            # Find all text elements that might contain total allowances
            col_elements = usage_container.find_elements(By.CSS_SELECTOR, ".col-xs-2.col-md-2.text-left")
            for i, element in enumerate(col_elements):
                text = element.text.strip()
                if "GB" in text:
                    if i == 0:
                        usage_data["Base Plan Total"] = text
                        print(f"Base Plan Total: {text}")
                    elif i == 1:
                        usage_data["Topup Total"] = text
                        print(f"Topup Total: {text}")
        except Exception as e:
            print(f"Could not extract total allowances: {e}")
        
        # Look for expiry information
        try:
            expiry_element = usage_container.find_element(By.CSS_SELECTOR, ".text-muted i")
            expiry_text = expiry_element.text.strip()
            if expiry_text:
                usage_data["Topup Expiry"] = expiry_text
                print(f"Topup Expiry: {expiry_text}")
        except Exception as e:
            print(f"Could not find expiry information: {e}")
        
        # Look for plan titles
        try:
            h5_elements = usage_container.find_elements(By.TAG_NAME, "h5")
            for h5 in h5_elements:
                h5_text = h5.text.strip()
                if h5_text:
                    print(f"Plan section found: {h5_text}")
        except Exception as e:
            print(f"Could not find plan titles: {e}")
            
    except TimeoutException:
        print("Timeout waiting for usage data container. Trying alternative approach...")
        
        # Alternative approach: look for all spans with usage data
        try:
            all_spans = driver.find_elements(By.CSS_SELECTOR, "span[style*='color:black']")
            for i, span in enumerate(all_spans):
                span_text = span.text.strip()
                if "GB" in span_text and "Used" in span_text:
                    usage_data[f"Usage Data {i+1}"] = span_text
                    print(f"Found usage data {i+1}: {span_text}")
        except Exception as e:
            print(f"Alternative approach failed: {e}")
            
    except Exception as e:
        print(f"Error scraping usage data: {e}")
    
    return usage_data

def setup_driver():
    """Initializes and returns a Chrome WebDriver instance."""
    options = Options()
    chrome_exe_paths_to_try = [
        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        rf"C:\\Users\\{os.getlogin()}\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"
    ]
    found_chrome_binary = False
    for path_option in chrome_exe_paths_to_try:
        if os.path.exists(path_option):
            options.binary_location = path_option
            print(f"Using Chrome binary location: {path_option}")
            found_chrome_binary = True
            break
    if not found_chrome_binary:
        print("WARNING: Chrome binary not found at common locations. Selenium will try to locate it automatically.")
        print(f"Looked in: {chrome_exe_paths_to_try}")

    try:
        raw_driver_path = ChromeDriverManager().install()
        print(f"Raw ChromeDriver Path from WDM: {raw_driver_path}")
    except Exception as e:
        print(f"Error calling ChromeDriverManager().install(): {e}")
        print("Please ensure webdriver-manager is installed and can access the internet.")
        return None

    normalized_driver_path = os.path.normpath(raw_driver_path)
    
    potential_path1 = os.path.join(os.path.dirname(normalized_driver_path), "chromedriver.exe")
    potential_path2 = os.path.join(os.path.dirname(os.path.dirname(normalized_driver_path)), "chromedriver.exe")

    corrected_driver_path = None
    if os.path.exists(potential_path1):
        corrected_driver_path = potential_path1
        print(f"Found ChromeDriver at: {corrected_driver_path}")
    elif os.path.exists(potential_path2):
        corrected_driver_path = potential_path2
        print(f"Found ChromeDriver at: {corrected_driver_path}")
    else:
        print(f"Initial path from WDM: {normalized_driver_path}")
        print(f"Checked for ChromeDriver at: {potential_path1}")
        print(f"Checked for ChromeDriver at: {potential_path2}")
        print("ERROR: ChromeDriver executable not found at expected locations within .wdm cache.")
        print("Please check the .wdm cache structure or webdriver-manager installation.")
        return None

    print(f"Using final ChromeDriver Path: {corrected_driver_path}")
    
    try:
        driver_service = Service(executable_path=corrected_driver_path)
        driver = webdriver.Chrome(service=driver_service, options=options)
        return driver
    except Exception as e:
        print(f"Error initializing webdriver.Chrome with path {corrected_driver_path}: {e}")
        return None

def main():
    usage_url = "https://app.imagine.com.bn/online_topup/usage.php"
    service_number, account_number = load_credentials()
    
    if not service_number or not account_number:
        print("Exiting script due to credential loading issues.")
        return
    
    # --- WebDriver Setup ---
    driver = setup_driver()
    if not driver:
        print("Failed to setup WebDriver. Exiting.")
        return

    driver.set_window_size(2576, 1396)
    
    print(f"Navigating to usage page: {usage_url}")
    driver.get(usage_url)
    
    try:
        # Wait for the service number field to be present and enter the service number
        print("Waiting for service number field...")
        service_number_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "txtServiceNo"))
        )
        service_number_field.click()
        service_number_field.clear()
        service_number_field.send_keys(service_number)
        print(f"Service number '{service_number}' entered.")
        
        # Wait for the account number field and enter the account number
        print("Waiting for account number field...")
        account_number_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "txtAccountNo"))
        )
        
        # Use ActionChains as shown in the Selenium IDE generated code
        actions = ActionChains(driver)
        actions.move_to_element(account_number_field).click_and_hold().perform()
        
        # Release the action
        element = driver.find_element(By.CSS_SELECTOR, ".headings")
        actions = ActionChains(driver)
        actions.move_to_element(element).release().perform()
        
        # Click on wrapper and then enter account number
        wrapper = driver.find_element(By.CSS_SELECTOR, ".wrapper")
        wrapper.click()
        
        account_number_field.clear()
        account_number_field.send_keys(account_number)
        print(f"Account number '{account_number}' entered.")
        
        # Find and click the check button
        print("Waiting for check button...")
        check_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "btnCheck"))
        )
        
        # Use ActionChains for the check button as shown in Selenium IDE code
        actions = ActionChains(driver)
        actions.move_to_element(check_button).click_and_hold().perform()
        
        # Release the action
        element = driver.find_element(By.CSS_SELECTOR, "center:nth-child(1)")
        actions = ActionChains(driver)
        actions.move_to_element(element).release().perform()
        
        print("Check button clicked. Waiting for results...")
        
        # Wait for form submission and results
        time.sleep(3)
          # Check if we successfully got to the results page
        if "usage.php" in driver.current_url:
            print("Successfully submitted form. Attempting to scrape usage data...")
            usage_data = scrape_usage_data(driver)
            
            if usage_data:
                print("\nUsage Data Retrieved:")
                for key, value in usage_data.items():
                    print(f"  {key}: {value}")
                
                # Prepare data for MQTT in the desired format
                mqtt_payload = {}
                if "Base Plan Usage" in usage_data:
                    try:
                        usage_string = usage_data["Base Plan Usage"]
                        parts = usage_string.lower().split('of')
                        used_part = parts[0].replace('gb', '').strip()
                        total_part = parts[1].split('gb')[0].strip()
                        
                        mqtt_payload['base_plan_used_gb'] = int(used_part)
                        mqtt_payload['base_plan_total_gb'] = int(total_part)
                        
                    except Exception as e:
                        print(f"Could not parse 'Base Plan Usage' string: '{usage_data['Base Plan Usage']}'. Error: {e}")
                        # mqtt_payload will remain empty or without these keys, so publishing will be skipped

                if 'base_plan_used_gb' in mqtt_payload and 'base_plan_total_gb' in mqtt_payload: # Condition reverted to use _gb keys
                    # Get current UTC time
                    utc_now = datetime.now(timezone.utc)
                    # Define Brunei timezone (UTC+8)
                    brunei_tz = timezone(timedelta(hours=8))
                    # Convert UTC time to Brunei time
                    brunei_now = utc_now.astimezone(brunei_tz)
                    # Format time string and append fixed offset
                    mqtt_payload['mqtt_timestamp'] = brunei_now.isoformat()
                    print(f"\nPrepared MQTT payload: {mqtt_payload}")
                    print("Attempting to publish data via MQTT...")
                    try:
                        if publish_imagine_json(mqtt_payload):
                            print("✅ Imagine data published successfully via MQTT.")
                        else:
                            print("❌ Failed to publish Imagine data via MQTT. Check mqtt_publisher logs for details.")
                    except Exception as e:
                        print(f"❌ An error occurred during MQTT publishing: {e}")
                else:
                    print("\nSkipping MQTT publish: Could not prepare 'base_plan_used_gb' and 'base_plan_total_gb' from scraped content.")                # Save to Excel using the exporter module
                try:
                    excel_path = export_imagine_data(usage_data)
                    if excel_path:
                        print(f"\nData successfully saved to {excel_path}")
                    else:
                        print("\nFailed to save data to Excel.")
                except Exception as e:
                    print(f"\nError saving data to Excel: {e}")
            else:
                print("No usage data could be retrieved.")
        else:
            print("Form submission may have failed or redirected to an unexpected page.")
            print(f"Current URL: {driver.current_url}")
            print(f"Page title: {driver.title}")
            
            # Print page source for debugging (first 1000 characters)
            print("Page source (first 1000 chars):")
            print(driver.page_source[:1000])
    
    except TimeoutException as te:
        print(f"A timeout occurred: {te}")
        print("Current page source (first 1000 chars):")
        print(driver.page_source[:1000])
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Current page source (first 1000 chars):")
        print(driver.page_source[:1000])
    
    finally:
        print("Closing the browser.")
        time.sleep(2)  # Brief pause before closing
        driver.quit()

if __name__ == "__main__":
    main()
