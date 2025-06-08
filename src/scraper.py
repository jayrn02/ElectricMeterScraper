from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import json # Added for loading credentials
import time
from mqtt_publisher import publish_usms_json # Added for MQTT publishing
import os # Added
from datetime import datetime, timezone, timedelta # Added timezone, timedelta
from excel_exporter import export_usms_data

from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options # Added
from webdriver_manager.chrome import ChromeDriverManager

# Function to load credentials from a JSON file
def load_credentials(file_path=None, service="USMS"):
    if file_path is None:
        # Get the directory where this script is located
        import os
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
            # Return username and password for USMS, or serviceNumber and accountNumber for other services
            if service == "USMS":
                return service_creds.get("username"), service_creds.get("password")
            elif service == "Imagine":
                return service_creds.get("serviceNumber"), service_creds.get("accountNumber")
            else:
                # For future services, you can add more conditions here
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

def scrape_data_from_table(driver):
    hourly_data = []
    total_consumption = None

    try:
        # Wait for the main data table to be present
        data_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ASPxPageControl1_grid_DXMainTable"))
        )
        print("Data table found.")

        # Find all data rows for hourly consumption
        # These rows have the class 'dxgvDataRow'
        data_rows = data_table.find_elements(By.CLASS_NAME, "dxgvDataRow")
        print(f"Found {len(data_rows)} hourly data rows.")

        for row in data_rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) == 2:
                hour = cols[0].text
                consumption = cols[1].text
                hourly_data.append({"hour": hour, "consumption_kWh": consumption})
            else:
                print(f"Skipping row with unexpected number of columns: {row.text}")

        # Find the footer row for total consumption
        # This row has the id 'ASPxPageControl1_grid_DXFooterRow'
        # It's inside a table with id 'ASPxPageControl1_grid_DXFooterTable'
        footer_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ASPxPageControl1_grid_DXFooterTable"))
        )
        footer_row = footer_table.find_element(By.ID, "ASPxPageControl1_grid_DXFooterRow")
        if footer_row:
            print("Footer row found.")
            cols = footer_row.find_elements(By.TAG_NAME, "td")
            if len(cols) == 2:
                # The total consumption is in the second 'td'
                # The text is like "Total units: 18.240"
                total_consumption_text = cols[1].text
                if "Total units:" in total_consumption_text:
                    total_consumption = total_consumption_text.split(":")[-1].strip()
            else:
                print(f"Footer row has unexpected number of columns: {footer_row.text}")
        else:
            print("Footer row not found.")

    except Exception as e:
        print(f"Error scraping data: {e}")

    return hourly_data, total_consumption

def scrape_dynamic_values(driver):
    """
    Scrapes specific labeled values (Remaining Unit, Remaining Balance, Last Updated) from the page.
    """
    values = {}
    try:
        # Switch to the iframe 'MyFrame' using its ID
        # Check if already in an iframe, and if so, switch to default content first
        # This is a guess, might need adjustment based on actual iframe structure
        try:
            driver.switch_to.default_content()
            print("Switched to default content before attempting to switch to MyFrame.")
        except Exception: # Might fail if not in an iframe, which is fine
            pass

        WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_it((By.ID, "MyFrame")))
        print("Switched to iframe 'MyFrame'.")

        # Define the labels and their corresponding XPath for the values
        labels_xpaths = {
            "Remaining Unit": "//*[@id='ASPxCardView1_DXCardLayout0_11']/table/tbody/tr/td[2]",
            "Remaining Balance": "//*[@id='ASPxCardView1_DXCardLayout0_12']/table/tbody/tr/td[2]",
            "Last Updated": "//*[@id='ASPxCardView1_DXCardLayout0_17']/table/tbody/tr/td[2]"
        }

        for label, xpath in labels_xpaths.items():
            try:
                # Wait for the element to be present
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                values[label] = element.text
                print(f"{label}: {element.text}")
            except TimeoutException:
                print(f"Error: Timed out waiting for {label} to load.")
                values[label] = None

        # Switch back to the default content after scraping
        driver.switch_to.default_content()
        print("Switched back to default content from MyFrame.")

    except Exception as e:
        print(f"Error scraping dynamic values: {e}")
        # Ensure we are back in default content in case of error during iframe operations
        try:
            driver.switch_to.default_content()
            print("Switched back to default content after error in dynamic values scraping.")
        except Exception:
            pass
    return values

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
    
    # Try to find chromedriver.exe
    # Path 1: In the same directory as the file WDM pointed to (e.g., .../chromedriver-win32/chromedriver.exe)
    potential_path1 = os.path.join(os.path.dirname(normalized_driver_path), "chromedriver.exe")
    # Path 2: In the parent directory of where WDM pointed (e.g., .../137.0.7151.68/chromedriver.exe)
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

# --- Configuration ---
login_url = "https://www.usms.com.bn/SmartMeter/resLogin"

# Load credentials from file
username, password = load_credentials() # Loads USMS credentials from credentials.json by default

if not username or not password:
    print("Exiting script due to credential loading issues.")
    exit() # Use exit() instead of quit() for script termination

# --- Element Locators (using NAME attribute from previous findings) ---
username_field_name = "ASPxRoundPanel1$txtUsername"
password_field_name = "ASPxRoundPanel1$txtPassword"
login_button_name = "ASPxRoundPanel1$btnLogin" # This was in the form data

# --- WebDriver Setup ---
driver = setup_driver()
if not driver:
    print("Failed to setup WebDriver. Exiting.")
    exit()

driver.set_window_size(1456, 1020)

print(f"Navigating to login page: {login_url}")
driver.get(login_url)

# Initialize scraped data variables here to ensure they exist in all paths
dynamic_values = {}
hourly_consumption = []
total_kwh = None

try:
    # Wait for the username field to be present and visible
    print("Waiting for username field (ID: ASPxRoundPanel1_txtUsername_I)...")
    username_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, "ASPxRoundPanel1_txtUsername_I"))
    )
    username_input.click()
    print("Username field clicked.")
    username_input.send_keys(username)
    print("Username entered.")

    # Find and fill the password field
    print("Waiting for password field (ID: ASPxRoundPanel1_txtPassword_I)...")
    password_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "ASPxRoundPanel1_txtPassword_I"))
    )
    password_input.click()
    print("Password field clicked.")
    password_input.send_keys(password)
    print("Password entered.")

    # Find and click the login button
    print("Waiting for login button (ID: ASPxRoundPanel1_btnLogin_CD)...")
    login_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, "ASPxRoundPanel1_btnLogin_CD"))
    )
    print("Login button is clickable. Attempting to click...")
    # Optional: Scroll into view if needed, though WebDriverWait usually handles visibility.
    # driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'center'});", login_button)
    # time.sleep(0.5) # Small pause before click, can be helpful
    login_button.click()
    print("Login button clicked.")

    print("Waiting up to 10 seconds for URL to change after login...")
    WebDriverWait(driver, 10).until(EC.url_changes(login_url))

    current_url = driver.current_url
    print(f"Current URL after login attempt: {current_url}")

    if "reslogin" not in current_url.lower():
        print("Login successful! URL has changed.")
        print(f"Now on page: {driver.current_url}")


    
        print("Allowing MainPage to settle for 3 seconds...")
        time.sleep(3)

        try:
            # Scrape dynamic values first as they are on the main page (inside MyFrame)
            dynamic_values = scrape_dynamic_values(driver) # Call to scrape dynamic values
            if dynamic_values:
                print(f"Dynamic Values: {dynamic_values}")
            else:
                print("Failed to retrieve dynamic values or no dynamic values found.")

            # Proceed with navigating to the consumption data page
            # This part assumes dynamic_values were scraped from 'MyFrame', and we are now in default content.
            # The next operations might be within the same 'MyFrame' or another one.
            # The original code switches to iframe by index 0 *after* this.
            # Let's ensure we are in the correct context or switch to the main iframe for consumption details.

            # Attempt to switch to the main content iframe if not already there or if operations require it.
            # This might be redundant if scrape_dynamic_values correctly returns to default_content
            # and the subsequent operations are within a new iframe context.
            # The original code had: WebDriverWait(driver, 20).until(EC.frame_to_be_available_and_switch_to_it(0))
            # This implies the consumption link is in the *first* iframe on the page.

            print("Attempting to switch to the main content iframe (index 0) for consumption details...")
            WebDriverWait(driver, 20).until(EC.frame_to_be_available_and_switch_to_it(0)) # Assumes this is the correct frame for consumption link
            print("Switched to main content iframe (index 0).")
            time.sleep(1) # Allow frame content to load

            print("Waiting for consumption image link (CSS: #ASPxCardView1_DXCardLayout0_cell0_18_ASPxHyperLink4_0 > img)...")
            consumption_link_img = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#ASPxCardView1_DXCardLayout0_cell0_18_ASPxHyperLink4_0 > img"))
            )
            print("Consumption image link found. Clicking...")
            consumption_link_img.click()
            print("Consumption image link clicked.")
            time.sleep(2) # Allow page to react

            print("Waiting for 'Type' dropdown trigger (ID: cboType_B-1Img)...")
            type_dropdown_trigger = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "cboType_B-1Img"))
            )
            type_dropdown_trigger.click()
            print("'Type' dropdown trigger clicked.")
            time.sleep(1) # Allow dropdown to appear

            print("Waiting for 'Type' option (ID: cboType_DDD_L_LBI3T0)...")
            type_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "cboType_DDD_L_LBI3T0"))
            )
            type_option.click()
            print("'Type' option selected.")
            time.sleep(1) # Allow selection to process

            print("Waiting for refresh button (CSS: #btnRefresh_CD > .dx-vam)...")
            refresh_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#btnRefresh_CD > .dx-vam"))
            )
            refresh_button.click()
            print("Refresh button clicked.")
            time.sleep(3) # Allow data to refresh

            print("Waiting for data tab/view (CSS: #ASPxPageControl1_T1T > .dx-vam)...")
            data_tab = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#ASPxPageControl1_T1T > .dx-vam"))
            )
            data_tab.click()
            print("Data tab/view clicked.")
            time.sleep(2) # Allow tab content to load

            # At this point, the page with the data table should be loaded.
            # Now, attempt to scrape data from the table.
            print("Attempting to scrape data from table...")
            hourly_consumption, total_kwh = scrape_data_from_table(driver)

            if hourly_consumption:
                print("\nHourly Consumption:")
                for item in hourly_consumption:
                    print(f"  Hour: {item['hour']}, kWh: {item['consumption_kWh']}")
            
            if total_kwh:
                print(f"\nTotal Consumption: {total_kwh} kWh")
            else:
                print("\nCould not retrieve total consumption.")            # --- Save to Excel ---
            if hourly_consumption:
                try:
                    excel_path = export_usms_data(
                        hourly_consumption=hourly_consumption,
                        total_kwh=total_kwh,
                        dynamic_values=dynamic_values
                    )
                    if excel_path:
                        print(f"\nData successfully saved to {excel_path}")
                    else:
                        print("\nFailed to save data to Excel.")
                except Exception as e:
                    print(f"\nError saving data to Excel: {e}")
            else:
                print("\nNo hourly data to save to Excel.")
            # --- End Save to Excel ---
            
            # --- MQTT Publishing ---
            mqtt_payload = {}
            if dynamic_values:
                mqtt_payload.update(dynamic_values) # Add all dynamic values
            
            # For hourly data, you might want to decide how to structure it.
            # Publishing a list of hourly readings might be too verbose for some MQTT use cases.
            # For now, let's add it directly.
            if hourly_consumption:
                mqtt_payload['hourly_consumption'] = hourly_consumption
            
            if total_kwh is not None: # Ensure total_kwh is not None before adding
                mqtt_payload['total_consumption_kwh'] = total_kwh
            
            if mqtt_payload: # Check if there's anything to publish
                # Convert to Brunei time (UTC+8)
                utc_now = datetime.now(timezone.utc)
                brunei_tz = timezone(timedelta(hours=8))
                brunei_now = utc_now.astimezone(brunei_tz)
                mqtt_payload['mqtt_timestamp'] = brunei_now.isoformat()
                print("\nAttempting to publish USMS data via MQTT...")
                try:
                    if publish_usms_json(mqtt_payload):
                        print("✅ USMS data published successfully via MQTT.")
                    else:
                        print("❌ Failed to publish USMS data via MQTT. Check mqtt_publisher logs for details.")
                except Exception as e:
                    print(f"❌ An error occurred during MQTT publishing for USMS data: {e}")
            else:
                print("\nSkipping MQTT publish for USMS: No data prepared.")
            # --- End MQTT Publishing ---

            # Switch back to default content if you need to interact outside the iframe later
            driver.switch_to.default_content()
            print("Switched back to default content after all operations in iframe.")

        except TimeoutException as nav_te:
            print(f"A timeout occurred during navigation or interaction after login: {nav_te}")
            try:
                driver.switch_to.default_content() # Ensure switch back on error
            except Exception:
                pass
        except Exception as nav_e:
            print(f"An error occurred after login: {nav_e}")
            try:
                driver.switch_to.default_content() # Ensure switch back on error
            except Exception:
                pass
        # ==============================================================================

    elif "Invalid IC Number or Password" in driver.page_source:
        print("Login failed: Invalid IC Number or Password message found on page.")
    elif username_field_name in driver.page_source: # Check if login fields are still present
        print("Login failed: Still on the login page (login fields detected).")
    else:
        print("Login status uncertain. Please check the browser window and console output.")
        print("Page title:", driver.title)

    print("Script finished checks. Browser will close shortly.")

except TimeoutException as te: # Catch TimeoutException specifically
    print(f"A timeout occurred during an explicit wait: {te}")
except Exception as e:
    print(f"An error occurred: {e}")

finally:
    print("Closing the browser.")
    driver.quit()
