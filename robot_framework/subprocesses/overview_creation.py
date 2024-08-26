""" This module automates the process of extracting data from STIL and
generates an overview. Export of results and errors to an Excel file and log files."""
from datetime import datetime
import os
import time
import shutil
import sys
import pyodbc
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
from openpyxl.worksheet.datavalidation import DataValidation


def initialize_browser(base_dir):
    """Initialize the Selenium Chrome WebDriver with download preferences. """
    download_dir = os.path.join(base_dir, "Exports")
    os.makedirs(download_dir, exist_ok=True)
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("test-type")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")

    return webdriver.Chrome(options=chrome_options)


def clear_base_directory(base_dir):
    """Delete all files and subdirectories within the base directory."""
    try:
        if os.path.exists(base_dir):
            shutil.rmtree(base_dir)
            print(f"Successfully cleared the directory: {base_dir}")
        else:
            print(f"The directory {base_dir} does not exist.")
    except TimeoutException as e:
        print(f"Timeout error: {e}")
    except NoSuchElementException as e:
        print(f"Element not found error: {e}")


def wait_for_download_completion(download_dir, timeout=60, retries=3):
    """Wait for the download process to complete with retries."""
    for attempt in range(retries):
        seconds = 0
        while seconds < timeout:
            time.sleep(1)
            files = os.listdir(download_dir)
            if any(file.endswith(".crdownload") for file in files):
                seconds += 1
            else:
                return True
        print(f"Retrying download check, attempt {attempt + 1}/{retries}")
    return False


def open_stil_connection(browser):
    """Opens STIL, waiting for user to log in."""
    browser.get("https://tilslutning.stil.dk/tilslutning/login")
    try:
        WebDriverWait(browser, 60).until(
            EC.presence_of_element_located((By.ID, "LoginMenuItem_2"))
        ).click()
        switch_to_new_tab(browser)
        WebDriverWait(browser, 60).until(
            EC.presence_of_element_located((By.ID, "ddlLocalIdPOrganization-input"))
        ).send_keys("Aarhus Kommune, 55133018, Aarhus Kommune")

        input_ddl = browser.find_element(By.ID, "ddlLocalIdPOrganization-input")
        input_ddl.click()
        submit_button = browser.find_element(By.ID, "btnSubmit")
        submit_button.click()

        print("Waiting for user to login...")

        WebDriverWait(browser, 300).until(
            EC.element_to_be_clickable((By.ID, "organisation-search"))
        )
        print("Login successful... Robot continues...")

    except (TimeoutException, NoSuchElementException) as e:
        print(f"Error during login: {str(e)}")
        browser.quit()
        sys.exit(1)


def switch_to_new_tab(browser):
    '''Switch to new tab.'''
    if len(browser.window_handles) > 1:
        browser.switch_to.window(browser.window_handles[1])


def fetch_aftaler(connection_string):
    """Fetch dataftaler from the database for error handling."""
    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT [InstRegNr], [Organisation]
            FROM [RPA].[rpa].[MBU003Dataaftaler]
            WHERE Organisation IN ('Dagtilbud', 'Institutioner')
        """)
        rows = cursor.fetchall()

        table_dagtilbud = [row for row in rows if row.Organisation == 'Dagtilbud']
        table_institution = [row for row in rows if row.Organisation == 'Institutioner']

        return table_dagtilbud, table_institution


def add_columns_to_dataframe(file_path, instregnr, organisation):
    """Read a CSV file and add 'Instregnr' and 'Organisation' columns."""
    try:
        df = pd.read_csv(file_path, delimiter=',', quotechar='"')
        df['Instregnr'] = instregnr
        df['Organisation'] = organisation

        return df
    except FileNotFoundError as e:
        print(f"File not found error: {e}")
        return None
    except pd.errors.ParserError as e:
        print(f"Error parsing file {file_path}: {e}")
        return None
    except pd.errors.EmptyDataError as e:
        print(f"Empty data error: {e}")
        return None


def click_element_with_retries(browser, by, value, retries=3):
    """Click an element with retries and handle common exceptions."""
    for attempt in range(retries):
        try:
            element = WebDriverWait(browser, 2).until(
                EC.visibility_of_element_located((by, value))
            )
            element.click()
            print(f"Successfully clicked element '{value}' on attempt {attempt + 1}")
            return True
        except (TimeoutException, ElementClickInterceptedException, StaleElementReferenceException) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(1)
    print(f"Failed to click element '{value}' after {retries} attempts")
    return False


def handle_notifications_popup(browser, notification_mail):
    """Handle the notification popups that may obstruct the automation process."""
    try:
        print("Trying to handle the notification popup")

        if not click_element_with_retries(browser, By.LINK_TEXT, 'Tilføj kontaktoplysninger'):
            print("Failed to click 'Tilføj kontaktoplysninger'.")
            return

        email_field = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.ID, 'notifikation-email'))
        )
        if email_field:
            email_field.send_keys(notification_mail)
            if not click_element_with_retries(browser, By.ID, 'opret-notifikation-button'):
                print("Failed to click 'Opret Notifikation' button.")
        else:
            print("Email field not found!")

        print("Trying to close the notification popup")
        if not click_element_with_retries(browser, By.XPATH, "//button[contains(text(), 'Luk')]"):
            print("Failed to close the notification popup.")

    except (TimeoutException, StaleElementReferenceException) as e:
        print(f"Error handling notification popup: {e}")


def process_organisation(browser, org, organisation_name, base_dir, result_df, error_log, notification_mail):
    """Process an organisation in STIL and download the data file."""
    max_attempts = 6  # Maximum number of retry attempts
    attempt = 0  # Current attempt

    while attempt < max_attempts:
        try:
            print(f"Processing organisation: {organisation_name}, InstRegNr: {org.InstRegNr}")
            browser.get('https://tilslutning.stil.dk/tilslutning?select-organisation=true')

            if organisation_name == "Dagtilbud":
                print("Switching to Dagtilbud tab...")
                dagtilbud_button = WebDriverWait(browser, 20).until(
                    EC.element_to_be_clickable((By.ID, "dagtilbud-tab-button"))
                )
                dagtilbud_button.click()

            row = WebDriverWait(browser, 20).until(
                EC.visibility_of_element_located((By.XPATH, f"//*[contains(text(), '{org.InstRegNr}')]"))
            )
            browser.execute_script("arguments[0].scrollIntoView(true);", row)
            click_element_with_retries(browser, By.XPATH, f"//*[contains(text(), '{org.InstRegNr}')]")
            print(f"Clicked row for {org.InstRegNr}...")

            result_df = process_data_for_organisation(browser, org, organisation_name, base_dir, result_df, error_log, notification_mail, attempt)
            if result_df is not None:
                print("colloumns added to dataframe.............................................................................Count Rows = ", len(result_df.index))
                return result_df  # Successfully processed
            attempt += 1

        except (TimeoutException, NoSuchElementException) as e:
            error_message = f"ERROR: Row not found or not clickable for {org.InstRegNr} on attempt {attempt + 1}, Exception: {str(e)}"
            error_log.append({'InstRegNr': org.InstRegNr, 'Organisation': organisation_name, 'Error': error_message})
            return result_df  # Exit on unrecoverable error
    return result_df


def process_data_for_organisation(browser, org, organisation_name, base_dir, result_df, error_log, notification_mail, attempt):
    """Handle the data processing logic for an organisation."""

    def handle_notification_and_click(browser):
        """Handles the notification popup and clicks the necessary elements."""
        try:
            notifications_close_button = WebDriverWait(browser, 5).until(
                EC.element_to_be_clickable((By.ID, "udbyder-close-button"))
            )
            if notifications_close_button:
                handle_notifications_popup(browser, notification_mail)
                return True
        except TimeoutException:
            pass

        return click_element_with_retries(browser, By.XPATH, "/html/body/div[1]/div/div[2]/div[2]/div/div[2]/div/h3/a")

    def check_data_requests(browser):
        """Check if there are any data requests for the organisation."""
        try:
            WebDriverWait(browser, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
            table_text = browser.find_element(By.TAG_NAME, 'body').text
            return "Endnu ingen forespørgsler på dataadgange." not in table_text
        except TimeoutException:
            return True  # Assume there are requests if timeout occurs

    def handle_file_download_and_processing(org, organisation_name, base_dir, result_df, attempt):
        """Handles file download and processing logic."""
        download_dir = os.path.join(base_dir, "Exports")
        processed_dir = os.path.join(download_dir, "processed")
        os.makedirs(processed_dir, exist_ok=True)

        if not wait_for_download_completion(download_dir):
            return log_error(f"ERROR: Download failed or timed out for {organisation_name}, InstRegNr: {org.InstRegNr} on attempt {attempt + 1}.")

        files_in_dir = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
        if not files_in_dir:
            return log_error(f"No files found in {download_dir} for {organisation_name}, InstRegNr: {org.InstRegNr} on attempt {attempt + 1}.")

        latest_file = max(files_in_dir, key=os.path.getctime)
        if not os.path.isfile(latest_file):
            return log_error(f"File {latest_file} not found after download on attempt {attempt + 1}. Download might have failed.")

        df = add_columns_to_dataframe(latest_file, org.InstRegNr, organisation_name)
        if df is None or df.empty:
            return log_error(f"Error processing file {latest_file} for {organisation_name}, InstRegNr: {org.InstRegNr} on attempt {attempt + 1}.")

        result_df = pd.concat([result_df, df], ignore_index=True)

        try:
            file_name = f"{org.InstRegNr}_{organisation_name}_processed.csv"
            new_file_path = os.path.join(processed_dir, file_name)
            shutil.move(latest_file, new_file_path)
            return result_df  # Successfully processed
        except (PermissionError, FileNotFoundError) as e:
            return log_error(f"Error moving file {latest_file} on attempt {attempt + 1}: {str(e)}")

    def log_error(error_message):
        """Logs the error."""
        error_log.append({'InstRegNr': org.InstRegNr, 'Organisation': organisation_name, 'Error': error_message})
        print(error_message)

    try:
        if not handle_notification_and_click(browser):
            return log_error(f"ERROR: Dataadministration button not found for {organisation_name}, InstRegNr: {org.InstRegNr} on attempt {attempt + 1}.")

        if not check_data_requests(browser):
            print(f"No data requests for {organisation_name}, InstRegNr: {org.InstRegNr}. Skipping processing.")
            return result_df

        if not click_element_with_retries(browser, By.CSS_SELECTOR, "button.stil-primary-button.hand.eksport-button"):
            return log_error(f"ERROR: Export button not found for {organisation_name}, InstRegNr: {org.InstRegNr} on attempt {attempt + 1}. No file downloaded.")

        return handle_file_download_and_processing(org, organisation_name, base_dir, result_df, attempt)

    except (TimeoutException, NoSuchElementException) as e:
        return log_error(f"ERROR: Row not found or not clickable for {org.InstRegNr} on attempt {attempt + 1}, Exception: {str(e)}")


def save_overview(result_df, base_dir, error_log):
    """Save the final DataFrame to an Excel file and configure data validation."""
    output_dir = os.path.join(base_dir, "Output")
    os.makedirs(output_dir, exist_ok=True)
    output_filename = "Dataaftaler_Oversigt_" + datetime.now().strftime('%d%m%Y') + ".xlsx"

    if not result_df.empty:
        result_df.insert(18, 'statusændring', '')
        result_df.sort_values(by='Instregnr', inplace=True)
        output_path = os.path.join(output_dir, output_filename)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False, sheet_name='Oversigt')
            worksheet = writer.sheets['Oversigt']
            worksheet.auto_filter.ref = worksheet.dimensions

            for row in range(2, worksheet.max_row + 1):
                status_cell = worksheet[f'R{row}']
                statusændring_cell = worksheet[f'S{row}']  # 'statusændring' is in column S
                if status_cell.value != "SLETTET":
                    dv = DataValidation(type="list", formula1='"GODKEND, SLET, VENT"')
                    dv.error_title = 'Invalid input'
                    dv.error_message = 'Please select a value from the dropdown list'
                    worksheet.add_data_validation(dv)
                    dv.add(statusændring_cell)

            # Adjust column widths but limit the max width
            max_column_width = 30
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        max_length = max(max_length, len(str(cell.value)))
                    except (TypeError, ValueError):
                        pass
                adjusted_width = min(max_length + 2, max_column_width)
                worksheet.column_dimensions[column].width = adjusted_width

    # Save Error Log
    output_dir = os.path.join(base_dir, "Output")
    if error_log:
        error_log_df = pd.DataFrame(error_log)
        error_log_filename = "Error_Log_" + datetime.now().strftime('%d%m%Y') + ".xlsx"
        error_log_path = os.path.join(output_dir, error_log_filename)
        error_log_df.to_excel(error_log_path, index=False, sheet_name='Errors')


def run_overview_creation(base_dir, connection_string, notification_mail):
    """Run the process of creating the overview of dataaftaler."""

    # Clear the base directory before processing
    clear_base_directory(base_dir)

    # Create necessary directories again
    os.makedirs(os.path.join(base_dir, "Exports"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "Output"), exist_ok=True)

    browser = initialize_browser(base_dir)

    result_df = pd.DataFrame()
    error_log = []

    try:
        open_stil_connection(browser)

        browser.get('https://tilslutning.stil.dk/tilslutning?select-organisation=true')
        WebDriverWait(browser, 60).until(
            EC.element_to_be_clickable((By.ID, "organisation-search"))
        )

        table_dagtilbud, table_institution = fetch_aftaler(connection_string)

        # Collect all unique InstRegNr for verification
        expected_instregnr = {org.InstRegNr for org in table_dagtilbud + table_institution}

        print("Processing institutioner tab...")
        for org in table_institution:
            result_df = process_organisation(browser, org, "Institutioner", base_dir, result_df, error_log, notification_mail)

        print("Processing dagtilbud tab...")
        for org in table_dagtilbud:
            result_df = process_organisation(browser, org, "Dagtilbud", base_dir, result_df, error_log, notification_mail)

    except TimeoutException as e:
        error_message = f"Timeout error occurred: {str(e)}"
        print(error_message)
        error_log.append({'InstRegNr': 'N/A', 'Organisation': 'N/A', 'Error': error_message})
    except NoSuchElementException as e:
        error_message = f"Element not found error occurred: {str(e)}"
        print(error_message)
        error_log.append({'InstRegNr': 'N/A', 'Organisation': 'N/A', 'Error': error_message})

    finally:
        # Verify if all expected InstRegNr have been processed
        expected_instregnr = set()
        unique_instregnr_in_results = set(result_df['Instregnr'].unique())
        missing_instregnr = expected_instregnr - unique_instregnr_in_results
        if missing_instregnr:
            error_message = f"ERROR: The following InstRegNr were expected but not processed: {', '.join(missing_instregnr)}"
            print(error_message)
            error_log.append("FINAL CHECK. THE FOLLOWING ORGANISATIONS WERE NOT FOUND IN OVERVIEW")
            for instregnr in missing_instregnr:
                error_log.append({'InstRegNr': instregnr, 'Organisation': 'Unknown', 'Error': 'File not found in overview.'})

        browser.quit()
        save_overview(result_df, base_dir, error_log)  # Save the final overview and error log
