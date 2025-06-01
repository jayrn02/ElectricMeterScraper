# Electric Meter Scraper

This project contains a Python script (`scraper.py`) that uses Selenium to log into the USMS Smart Meter website (https://www.usms.com.bn/SmartMeter/resLogin) and scrape electric meter consumption data.

## Features

*   Logs into the website using provided credentials.
*   Navigates to the hourly consumption data page.
*   Scrapes hourly data and total consumption.
*   Prints the scraped data to the console.

## Setup

1.  **Install Python:** If you don't have Python installed, download and install it from [python.org](https://www.python.org/).
2.  **Install Selenium:** Open your terminal or command prompt and install the Selenium library:
    ```bash
    pip install selenium
    ```
3.  **WebDriver:**
    *   Download the ChromeDriver that matches your version of Google Chrome from [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads).
    *   Place `chromedriver.exe` in the same directory as `scraper.py`, or ensure it's in your system's PATH.

## Running the Scraper

...
