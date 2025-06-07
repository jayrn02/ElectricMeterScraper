from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import json # Added for loading credentials
import time
import pandas as pd # Added for Excel export

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
        print("Switched back to default content.")

    except Exception as e:
        print(f"Error scraping dynamic values: {e}")

    return values

# --- Configuration ---
login_url = "https://www.usms.com.bn/SmartMeter/resLogin"

# Load credentials from file
username, password = load_credentials() # Loads USMS credentials from credentials.json by default

if not username or not password:
    print("Exiting script due to credential loading issues.")
    exit()

# Path to your WebDriver executable (e.g., "chromedriver.exe" or "msedgedriver.exe")
# If the WebDriver is in your system PATH or same directory as the script, you can just use its name.
# webdriver_path = "chromedriver.exe" # Example for Chrome, adjust if needed or if it's in PATH

# --- Element Locators (using NAME attribute from previous findings) ---
username_field_name = "ASPxRoundPanel1$txtUsername"
password_field_name = "ASPxRoundPanel1$txtPassword"
login_button_name = "ASPxRoundPanel1$btnLogin" # This was in the form data

# Initialize the WebDriver (using Chrome in this example)
# driver = webdriver.Chrome(executable_path=webdriver_path) # Use this if webdriver_path is set
driver = webdriver.Chrome() 
driver.set_window_size(1456, 1020) 

print(f"Navigating to login page: {login_url}")
driver.get(login_url)

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
            dynamic_values = scrape_dynamic_values(driver)
            if dynamic_values:
                print(f"Dynamic Values: {dynamic_values}")
            else:
                print("Failed to retrieve dynamic values.")

            print("Switching to iframe (index 0)...")
            WebDriverWait(driver, 20).until(EC.frame_to_be_available_and_switch_to_it(0))
            print("Switched to iframe.")
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
                print("\nCould not retrieve total consumption.")

            # --- Save to Excel ---
            if hourly_consumption:
                try:
                    df = pd.DataFrame(hourly_consumption)
                    # For now, we'll just save hourly data. We can add total_kwh later.
                    excel_file_path = r"C:\Users\jayre\Desktop\MeterData.xlsx"
                    df.to_excel(excel_file_path, index=False, sheet_name="Hourly Consumption")
                    print(f"\nData successfully saved to {excel_file_path}")
                except Exception as e:
                    print(f"\nError saving data to Excel: {e}")
            else:
                print("\nNo hourly data to save to Excel.")
            # --- End Save to Excel ---

            # Call scrape_dynamic_value after navigation and actions


            # Switch back to default content if you need to interact outside the iframe later
            # driver.switch_to.default_content()

        except TimeoutException as nav_te:
            print(f"A timeout occurred during navigation or interaction after login: {nav_te}")
        except Exception as nav_e:
            print(f"An error occurred after login: {nav_e}")
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
