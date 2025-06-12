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
from excel_exporter import export_usms_data # Ensure this line is present

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
    """
    Version 2: Simulates data scraping without actually extracting data.
    Goes through the motions but returns empty/mock data.
    """
    hourly_data = []
    total_consumption = None

    try:
        # Wait for the main data table to be present (same as V1)
        data_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ASPxPageControl1_grid_DXMainTable"))
        )
        print("Data table found.")

        # Find all data rows for hourly consumption (but don't extract data)
        data_rows = data_table.find_elements(By.CLASS_NAME, "dxgvDataRow")
        print(f"Found {len(data_rows)} hourly data rows.")
        
        # Simulate processing rows without extracting data
        for i, row in enumerate(data_rows):
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) == 2:
                # Instead of extracting actual data, use mock data
                hour = f"Hour {i+1}"
                consumption = "0.000"
                hourly_data.append({"hour": hour, "consumption_kWh": consumption})
                print(f"  Simulated row {i+1}: {hour} - {consumption} kWh")
            else:
                print(f"Skipping row with unexpected number of columns: row index {i}")

        # Find the footer row for total consumption (but don't extract data)
        footer_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ASPxPageControl1_grid_DXFooterTable"))
        )
        footer_row = footer_table.find_element(By.ID, "ASPxPageControl1_grid_DXFooterRow")
        if footer_row:
            print("Footer row found.")
            cols = footer_row.find_elements(By.TAG_NAME, "td")
            if len(cols) == 2:
                # Simulate total consumption without extracting actual data
                total_consumption = "0.000"
                print(f"  Simulated total consumption: {total_consumption} kWh")
            else:
                print("Footer row has unexpected number of columns: row found but structure unexpected")
        else:
            print("Footer row not found.")

    except Exception as e:
        print(f"Error during table simulation: {e}")

    return hourly_data, total_consumption

def scrape_meter_data(driver, meter_index):
    """
    Version 2: Scrapes actual meter data (same as V1).
    The difference from V1 is that V2 doesn't scrape the table data at the end.
    """
    meter_data = {}
    meter_type = "Electricity" if meter_index == 0 else "Water"
    
    try:
        # Define the selectors for this specific meter (same as V1)
        base_id = f"ASPxCardView1_DXCardLayout{meter_index}"
        
        # Collect all fields for both meter types (same selectors as V1)
        fields = {
            "Meter No": f"#{base_id}_2 .dxflNestedControlCell",
            "Full Name": f"#{base_id}_4 .dxflNestedControlCell", 
            "Meter Status": f"#{base_id}_5 .dxflNestedControlCell",
            "Address": f"#{base_id}_6 .dxflNestedControlCell",
            "Kampong": f"#{base_id}_7 .dxflNestedControlCell",
            "Mukim": f"#{base_id}_8 .dxflNestedControlCell",
            "District": f"#{base_id}_9 .dxflNestedControlCell",
            "Postcode": f"#{base_id}_10 .dxflNestedControlCell",
            "Remaining Unit": f"#{base_id}_11 .dxflNestedControlCell",
            "Remaining Balance": f"#{base_id}_12 .dxflNestedControlCell",
            "Last Updated": f"#{base_id}_17 .dxflNestedControlCell"
        }

        print(f"\nScraping {meter_type} meter data...")
        
        for field_name, css_selector in fields.items():
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
                )
                # Extract actual data (same as V1)
                meter_data[field_name] = element.text.strip()
                print(f"  {field_name}: {element.text.strip()}")
            except TimeoutException:
                print(f"  Error: Timed out waiting for {field_name} to load.")
                meter_data[field_name] = None
            except Exception as e:
                print(f"  Error getting {field_name}: {e}")
                meter_data[field_name] = None
                
        # Add meter type for identification
        meter_data["Meter Type"] = meter_type
        
    except Exception as e:
        print(f"Error scraping {meter_type} meter data: {e}")
        
    return meter_data

def scrape_all_meters(driver):
    """
    Version 2: Scrapes actual data from all available meters (same as V1).
    The difference from V1 is that V2 doesn't scrape the table data at the end.
    """
    all_meters = {}
    
    try:
        # Switch to the iframe 'MyFrame' using its ID (same as V1)
        try:
            driver.switch_to.default_content()
            print("Switched to default content before attempting to switch to MyFrame.")
        except Exception:
            pass

        WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_it((By.ID, "MyFrame")))
        print("Switched to iframe 'MyFrame'.")

        # Check which meters are available by looking for their card elements (same as V1)
        available_meters = []
        # Check for electricity meter (index 0)
        try:
            driver.find_element(By.ID, "ASPxCardView1_DXDataCard0")
            available_meters.append((0, "Electricity"))
            print("Electricity meter found.")
        except Exception:
            print("Electricity meter not found.")
            
        # Check for water meter (index 1) 
        try:
            driver.find_element(By.ID, "ASPxCardView1_DXDataCard1")
            available_meters.append((1, "Water"))
            print("Water meter found.")
        except Exception:
            print("Water meter not found.")
              # Scrape data from each available meter
        for meter_index, meter_name in available_meters:
            meter_data = scrape_meter_data(driver, meter_index)
            # Add script execution timestamp to each meter (same as V1)
            if meter_data:
                utc_now = datetime.now(timezone.utc)
                brunei_tz = timezone(timedelta(hours=8))
                brunei_now = utc_now.astimezone(brunei_tz)
                meter_data['Script Execution Time'] = brunei_now.isoformat()
            all_meters[meter_name.lower()] = meter_data        # Switch back to the default content after scraping (same as V1)
        driver.switch_to.default_content()
        print("Switched back to default content from MyFrame.")

    except Exception as e:
        print(f"Error scraping meter data: {e}")
        try:
            driver.switch_to.default_content()
            print("Switched back to default content after error in meter data scraping.")
        except Exception:
            pass
            
    return all_meters

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
    exit()

# --- Element Locators (using NAME attribute from previous findings) ---
username_field_name = "ASPxRoundPanel1$txtUsername"
password_field_name = "ASPxRoundPanel1$txtPassword"
login_button_name = "ASPxRoundPanel1$btnLogin"

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

        try:            # Scrape all meter data (electricity and water meters)
            all_meter_data = scrape_all_meters(driver)
            if all_meter_data:
                print(f"Meter Data: {all_meter_data}")
            else:
                print("Failed to retrieve meter data or no meters found.")

            # For backward compatibility, extract electricity meter data as dynamic_values
            dynamic_values = {}
            if 'electricity' in all_meter_data:
                elec_data = all_meter_data['electricity']
                dynamic_values = {
                    "Remaining Unit": elec_data.get("Remaining Unit"),
                    "Remaining Balance": elec_data.get("Remaining Balance"), 
                    "Last Updated": elec_data.get("Last Updated")
                }            # V2: Stop here! We have all the meter data we need.

            if all_meter_data:
                try:
                    # Ensure we are calling export_usms_data correctly
                    excel_path = export_usms_data(
                        hourly_consumption=[],  # Empty list as per existing V2 logic
                        total_kwh=None,        # None as per existing V2 logic
                        dynamic_values=dynamic_values, # Pass existing dynamic_values
                        all_meter_data=all_meter_data  # Pass the main meter data
                    )
                    if excel_path:
                        print(f"\\nData successfully saved to {excel_path}")
                    else:
                        print("\\nFailed to save data to Excel.")
                except Exception as e:
                    print(f"\\nError saving data to Excel: {e}")
            else:
                print("\\nNo meter data to save to Excel.")
                
            # MQTT Publishing: Prepare separate payloads for electricity and water
            electricity_payload = None
            water_payload = None
            data_to_publish_exists = False

            if all_meter_data:
                utc_now = datetime.now(timezone.utc)
                brunei_tz = timezone(timedelta(hours=8))
                brunei_now_iso = utc_now.astimezone(brunei_tz).isoformat()

                desired_keys_for_mqtt = ["Remaining Unit", "Remaining Balance", "Last Updated"]

                if 'electricity' in all_meter_data and all_meter_data['electricity']:
                    source_data_elec = all_meter_data['electricity']
                    temp_payload_elec = {}
                    for key in desired_keys_for_mqtt:
                        if key in source_data_elec and source_data_elec[key] is not None:
                            temp_payload_elec[key] = source_data_elec[key]
                    
                    if temp_payload_elec: # If any of the desired keys were found and have values
                        electricity_payload = temp_payload_elec
                        electricity_payload['mqtt_timestamp'] = brunei_now_iso
                        data_to_publish_exists = True
                    # else electricity_payload remains None, and data_to_publish_exists is not set to True here

                if 'water' in all_meter_data and all_meter_data['water']:
                    source_data_water = all_meter_data['water']
                    temp_payload_water = {}
                    for key in desired_keys_for_mqtt:
                        if key in source_data_water and source_data_water[key] is not None:
                            temp_payload_water[key] = source_data_water[key]

                    if temp_payload_water: # If any of the desired keys were found and have values
                        water_payload = temp_payload_water
                        water_payload['mqtt_timestamp'] = brunei_now_iso
                        data_to_publish_exists = True # Set to true if water data is being published
                    # else water_payload remains None
            
            if data_to_publish_exists:
                print("\\\\nAttempting to publish USMS data via MQTT to respective topics...")
                try:
                    # Call the modified publish_usms_json with separate payloads
                    if publish_usms_json(electricity_payload, water_payload):
                        print("✅ USMS data (electricity and/or water) published successfully via MQTT.")
                    else:
                        print("❌ Failed to publish some or all USMS data via MQTT. Check mqtt_publisher logs for details.")
                except Exception as e:
                    print(f"❌ An error occurred during MQTT publishing for USMS data: {e}")
            else:
                print("\\nSkipping MQTT publish for USMS: No data prepared.")

            print("\\n🎯 usmsScraperV2 completed successfully!")
            print("Collected meter data without navigating to consumption tables.")

        except TimeoutException as nav_te:
            print(f"A timeout occurred during navigation or interaction after login: {nav_te}")
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
        except Exception as nav_e:
            print(f"An error occurred after login: {nav_e}")
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

    elif "Invalid IC Number or Password" in driver.page_source:
        print("Login failed: Invalid IC Number or Password message found on page.")
    elif username_field_name in driver.page_source:
        print("Login failed: Still on the login page (login fields detected).")
    else:
        print("Login status uncertain. Please check the browser window and console output.")
        print("Page title:", driver.title)

    print("Script finished checks. Browser will close shortly.")

except TimeoutException as te:
    print(f"A timeout occurred during an explicit wait: {te}")
except Exception as e:
    print(f"An error occurred: {e}")

finally:
    print("Closing the browser.")
    driver.quit()
