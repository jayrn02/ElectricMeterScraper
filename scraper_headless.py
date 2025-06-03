from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
import time
import json # Added for loading credentials

# Function to load credentials from a JSON file
def load_credentials(file_path="credentials.json"):
    try:
        with open(file_path, 'r') as f:
            creds = json.load(f)
            return creds["username"], creds["password"]
    except FileNotFoundError:
        print(f"Error: Credentials file '{file_path}' not found.")
        return None, None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{file_path}'.")
        return None, None
    except KeyError:
        print(f"Error: 'username' or 'password' key not found in '{file_path}'.")
        return None, None

def scrape_data_from_table(driver):
    """
    Scrapes hourly and total consumption data from the table.
    Assumes the driver is on the page containing the table.
    """
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

# --- Configuration ---
login_url = "https://www.usms.com.bn/SmartMeter/resLogin"

# Load credentials from file
username, password = load_credentials() # Loads from credentials.json by default

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

# Initialize the WebDriver with headless mode
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1456,1020")

# Use the headless Chrome driver
# driver = webdriver.Chrome(executable_path=webdriver_path, options=chrome_options) # Use this if webdriver_path is set
driver = webdriver.Chrome(options=chrome_options)
driver.set_window_size(1456, 1020) 

print(f"Navigating to login page: {login_url}")
driver.get(login_url)

try:
    # Wait for the username field to be present and visible
    print("Waiting for username field (ID: ASPxRoundPanel1_txtUsername_I) to be clickable...")
    username_input = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, "ASPxRoundPanel1_txtUsername_I"))
    )
    username_input.click()
    print("Username field clicked.")
    username_input.send_keys(username)
    print("Username entered.")

    # Click to focus or dismiss pop-up after username, from test_meter3.py
    print("Clicking table cell (CSS: tr:nth-child(5) > td)...")
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "tr:nth-child(5) > td"))
    ).click()
    print("Table cell clicked.")

    # Find and fill the password field
    print("Waiting for password field (ID: ASPxRoundPanel1_txtPassword_I) to be clickable...")
    password_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "ASPxRoundPanel1_txtPassword_I"))
    )
    password_input.click()
    print("Password field clicked.")
    password_input.send_keys(password)
    print("Password entered.")

    # Find and click the login button
    print("Waiting for login button (CSS: #ASPxRoundPanel1_btnLogin_CD > .dx-vam) to be clickable...")
    login_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#ASPxRoundPanel1_btnLogin_CD > .dx-vam"))
    )
    print("Login button is clickable. Attempting to click...")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'center'});", login_button)
    time.sleep(0.5)
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
            print("Switching to iframe (index 0)...")
            WebDriverWait(driver, 20).until(EC.frame_to_be_available_and_switch_to_it(0))
            print("Switched to iframe.")
            time.sleep(1)

            print("Waiting for consumption image link (CSS: #ASPxCardView1_DXCardLayout0_cell0_18_ASPxHyperLink4_0 > img)...")
            consumption_link_img = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#ASPxCardView1_DXCardLayout0_cell0_18_ASPxHyperLink4_0 > img"))
            )
            print("Consumption image link found. Clicking...")
            consumption_link_img.click()
            print("Consumption image link clicked.")
            time.sleep(3)

            print("Waiting for 'Type' dropdown (ID: cboType_I)...")
            type_dropdown = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "cboType_I")))
            type_dropdown.click()
            print("'Type' dropdown clicked.")
            time.sleep(1)

            print("Waiting for 'Type' option (ID: cboType_DDD_L_LBI3T0)...")
            type_option = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "cboType_DDD_L_LBI3T0")))
            type_option.click()
            print("'Type' option selected.")
            time.sleep(1)

            print("Interacting with 'Date From' (ID: cboDateFrom_I)...")
            date_from_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "cboDateFrom_I")))
            date_from_input.click()
            time.sleep(0.5)
            date_from_input.click()
            time.sleep(0.5)
            
            print("Clicking to close calendar/focus (CSS: #UpdatePanel1 > div > table > tbody > tr:nth-child(3))...")
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#UpdatePanel1 > div > table > tbody > tr:nth-child(3)"))
            ).click()
            time.sleep(0.5)

            print("Sending keys '29-5-25' to 'Date From'...")
            date_from_input.clear()
            date_from_input.send_keys("29-5-25")
            print("'Date From' set.")
            time.sleep(1)

            # Interact with "Date To"
            print("Interacting with 'Date To' (ID: cboDateTo_I)...")
            
            # Explicitly wait for the known overlay to be gone before interacting with date input
            overlay_id = "pcErr_DXPWMB-1"
            print(f"Checking for overlay {overlay_id} and waiting for it to be invisible...")
            try:
                WebDriverWait(driver, 15).until( # Increased wait time slightly
                    EC.invisibility_of_element_located((By.ID, overlay_id))
                )
                print(f"Overlay {overlay_id} is invisible or gone.")
            except TimeoutException:
                print(f"Overlay {overlay_id} did not disappear. Attempting to send ESCAPE key...")
                try:
                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                    print("Sent ESCAPE key.")
                    time.sleep(1) # Give it a moment to react
                except Exception as esc_e:
                    print(f"Could not send ESCAPE key: {esc_e}")

            # Now, attempt to click the date input field
            date_to_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "cboDateTo_I")))
            print("Attempting to click 'Date To' input field...")
            try:
                date_to_input.click()
                print("'Date To' input field clicked normally.")
            except Exception as e:
                print(f"Normal click on 'Date To' failed: {type(e).__name__} - {e}. Attempting JavaScript click.")
                driver.execute_script("arguments[0].click();", date_to_input)
                print("'Date To' input field clicked using JavaScript.")
            time.sleep(0.5)

            print("Clicking related to date picker (CSS: tr:nth-child(3) > td > table > tbody > tr)...")
            WebDriverWait(driver, 10).until(
                 EC.element_to_be_clickable((By.CSS_SELECTOR, "tr:nth-child(3) > td > table > tbody > tr"))
            ).click()
            print("Clicked element related to date picker.")
            time.sleep(0.5)

            # Re-fetch element before send_keys for robustness
            print("Re-fetching 'Date To' input element before sending keys...")
            date_to_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "cboDateTo_I")))
            print("Sending keys '29-5-25' to 'Date To'...")
            date_to_input.clear()
            date_to_input.send_keys("29-5-25")
            print("'Date To' set.")
            time.sleep(1)

            print("Waiting for 'Refresh' button (CSS: #btnRefresh_CD > .dx-vam)...")
            refresh_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#btnRefresh_CD > .dx-vam"))
            )
            refresh_button.click()
            print("'Refresh' button clicked.")
            time.sleep(5)

            print("Waiting for 'Hourly Consumption' tab (CSS: #ASPxPageControl1_T1T > .dx-vam)...")
            hourly_tab = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#ASPxPageControl1_T1T > .dx-vam"))
            )
            hourly_tab.click()
            print("'Hourly Consumption' tab clicked.")
            time.sleep(5)

            print(f"Current URL after navigation: {driver.current_url}")
            print(f"Page title after navigation: {driver.title}")

            print("Attempting to scrape data from the table...")
            hourly_data, total_kwh = scrape_data_from_table(driver)

            if hourly_data:
                print("\nHourly Consumption Data:")
                for item in hourly_data:
                    print(f"  Hour: {item['hour']}, kWh: {item['consumption_kWh']}")
            else:
                print("\nNo hourly consumption data found or scraped.")

            if total_kwh:
                print(f"\nTotal Consumption: {total_kwh} kWh")
            else:
                print("\nCould not retrieve total consumption.")
            
        except TimeoutException as nav_te:
            print(f"Timeout during post-login navigation: {nav_te}")
        except Exception as nav_e:
            print(f"An error occurred during post-login navigation or scraping: {nav_e}")
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

# Example of how you might call this function after successful login and navigation:
# if __name__ == "__main__":
#     # ... (your existing login and navigation code) ...
#     # driver = ... (your initialized and navigated WebDriver)
#
#     # Assuming login and navigation were successful and driver is on the correct page
#     # For demonstration, let's simulate the driver being on the page
#     # In a real scenario, this would be after your login and navigation steps
#
#     # ---- Placeholder for your actual driver initialization and navigation ----
#     # from selenium import webdriver
#     # from selenium.webdriver.chrome.service import Service as ChromeService
#     # from webdriver_manager.chrome import ChromeDriverManager
#     #
#     # options = webdriver.ChromeOptions()
#     # # options.add_argument('--headless') # Optional: run headless
#     # options.add_argument('--disable-gpu') # Optional: recommended for headless
#     # options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
#     #
#     # print("Initializing WebDriver...")
#     # driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
#     # print("WebDriver initialized.")
#     #
#     # # --- IMPORTANT: Replace this with actual navigation to the data page ---
#     # # driver.get("your_data_page_url_here_after_login")
#     # # For this example, we can't actually log in, so this part is illustrative.
#     # # You would call scrape_data_from_table(driver) AFTER you are on the page
#     # # that contains the HTML snippet you provided.
#     #
#     # # If you have the HTML content locally for testing this function, you could load it:
#     # # import os
#     # # current_dir = os.path.dirname(os.path.abspath(__file__))
#     # # html_file_path = os.path.join(current_dir, "temp_data_page.html") # Save your HTML snippet to this file
#     # # with open(html_file_path, "w", encoding="utf-8") as f:
#     # #     f.write(\'\'\'YOUR_HTML_SNIPPET_HERE\'\'\') # Paste the long HTML here
#     # # driver.get("file://" + html_file_path)
#     # # time.sleep(2) # Allow page to load
#     # # --------------------------------------------------------------------
#
#     # hourly_consumption, total_kwh = scrape_data_from_table(driver)
#
#     # if hourly_consumption:
#     #     print("\\nHourly Consumption:")
#     #     for item in hourly_consumption:
#     #         print(f"  Hour: {item['hour']}, kWh: {item['consumption_kWh']}")
#
#     # if total_kwh:
#     #     print(f"\\nTotal Consumption: {total_kwh} kWh")
#     # else:
#     #     print("\\nCould not retrieve total consumption.")
#
#     # driver.quit() # Make sure to quit the driver when done

# The main part of the script (login, etc.) would go above or call this function.
# For now, this function is defined and can be called once the driver is on the correct page.

