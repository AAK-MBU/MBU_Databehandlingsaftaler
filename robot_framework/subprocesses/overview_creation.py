""" This module automates the process of extracting data from STIL and 
generates an overview.

Key Features:
- Browser automation with Selenium for data export.
- Database querying with pyodbc to fetch relevant data.
- Data processing and validation with pandas.
- Error handling and logging to track any issues during execution.
- Export of results and errors to an Excel file and log files."""
from datetime import datetime
import os
import pandas as pd
import pyodbc
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from openpyxl.worksheet.datavalidation import DataValidation


def initialize_browser(base_dir):
    """
    Initialize the Selenium Chrome WebDriver with download preferences.

    Args:
        base_dir (str): The base directory for all Dataaftale-processes.

    Returns:
        webdriver.Chrome: Configured Selenium WebDriver instance.
    """
    download_dir = os.path.join(base_dir, "Exports")
    os.makedirs(download_dir, exist_ok=True)
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    return webdriver.Chrome(options=chrome_options)


def wait_for_download_completion(download_dir, timeout=60):
    """
    Wait for the download process to complete.

    Args:
        download_dir (str): Directory to check for download completion.
        timeout (int): Maximum wait time in seconds.

    Returns:
        bool: True if download completes within timeout.
    """
    seconds = 0
    while seconds < timeout:
        time.sleep(1)
        files = os.listdir(download_dir)
        if any(file.endswith(".crdownload") for file in files):
            seconds += 1
        else:
            return True
    return False


def open_stil_connection(browser):
    """
    Opens STIL, waiting for user to log in.

    Args:
        browser (webdriver.Chrome): The Selenium WebDriver instance.

    Returns:
        None
    """
    browser.get("https://tilslutning.stil.dk/tilslutning/login")
    try:
        WebDriverWait(browser, 60).until(EC.presence_of_element_located((By.ID, "LoginMenuItem_2"))).click()
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
        exit(1)


def switch_to_new_tab(browser):
    if len(browser.window_handles) > 1:
        browser.switch_to.window(browser.window_handles[1])


def fetch_aftaler(connection_string):
    """
    Fetch agreements from the SQL database based on specific criteria.

    Args:
        connection_string (str): Connection string for the SQL database.

    Returns:
        tuple: Two lists of agreements categorized as 'Dagtilbud' and 'Institutioner'.
    """
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
    """
    Read a CSV file and add 'Instregnr' and 'Organisation' columns.

    Args:
        file_path (str): Path to the CSV file.
        instregnr (str): Institution registration number.
        organisation (str): Organisation name.

    Returns:
        pd.DataFrame: DataFrame with additional columns or None if an error occurs.
    """
    try:
        # Read the CSV file
        df = pd.read_csv(file_path, delimiter=',', quotechar='"')
        
        # Add the new columns
        df['Instregnr'] = instregnr
        df['Organisation'] = organisation

        print(df.head())
        
        return df
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return None


def process_organisation(browser, org, organisation_name, base_dir, result_df, error_log):
    """
    Process data for an organisation by exporting and adding it to the result DataFrame.

    Args:
        browser (webdriver.Chrome): The Selenium WebDriver instance.
        org (pyodbc.Row): Organisation record from the database.
        organisation_name (str): Name of the organisation.
        base_dir (str): Base directory for all Dataaftale-processes. 
        result_df (pd.DataFrame): DataFrame to which processed data is appended.
        error_log (list): List to store errors encountered during processing.

    Returns:
        pd.DataFrame: Updated DataFrame with the new data.
    """
    try:
        browser.get('https://tilslutning.stil.dk/tilslutning?select-organisation=true')
        if organisation_name == "Dagtilbud":
            dagtilbud_button = WebDriverWait(browser, 20).until(
                EC.element_to_be_clickable((By.ID, "dagtilbud-tab-button"))
            )
            dagtilbud_button.click()

        row = WebDriverWait(browser, 20).until(
            EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{org.InstRegNr}')]"))
        )
        row.click()
        close_notifications_popup(browser)
        WebDriverWait(browser, 50).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "Dataadgangadministration"))
        ).click()

        try:
            WebDriverWait(browser, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.stil-primary-button.hand.eksport-button"))
            )
        except TimeoutException:
            error_message = f"ERROR: Export button not found for organisation: {organisation_name}, InstRegNr: {org.InstRegNr}. No file downloaded. (No dataaftaler?)"
            error_log.append({'InstRegNr': org.InstRegNr, 'Organisation': organisation_name, 'Error': error_message})
            return result_df
        
        export_button = browser.find_element(By.CSS_SELECTOR, "button.stil-primary-button.hand.eksport-button")
        if export_button:
            export_button.click()
            download_dir = os.path.join(base_dir, "Exports")
            if wait_for_download_completion(download_dir):
                files_in_dir = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
                if not files_in_dir:
                    error_message = f"No files found in {download_dir} for organisation: {organisation_name}, InstRegNr: {org.InstRegNr}."
                    error_log.append({'InstRegNr': org.InstRegNr, 'Organisation': organisation_name, 'Error': error_message})
                    return result_df

                latest_file = max(files_in_dir, key=os.path.getctime)
                instregnr = org.InstRegNr
                df = add_columns_to_dataframe(latest_file, instregnr, organisation_name)
                print("Columns added to the dataframe...")
                if df is not None:
                    result_df = pd.concat([result_df, df], ignore_index=True)
                else:
                    error_message = f"Error processing file {latest_file} for organisation: {organisation_name}, InstRegNr: {org.InstRegNr}."
                    error_log.append({'InstRegNr': org.InstRegNr, 'Organisation': organisation_name, 'Error': error_message})

                os.remove(latest_file)
                browser.get('https://tilslutning.stil.dk/tilslutning?select-organisation=true')
            else:
                error_message = f"ERROR: Download failed or timed out for organisation: {organisation_name}, InstRegNr: {instregnr}."
                error_log.append({'InstRegNr': instregnr, 'Organisation': organisation_name, 'Error': error_message})
        else:
            error_message = f"ERROR: Export button not found for organisation: {organisation_name}, InstRegNr: {instregnr}. No file downloaded. (No dataaftaler?)"
            error_log.append({'InstRegNr': instregnr, 'Organisation': organisation_name, 'Error': error_message})

    except (TimeoutException, NoSuchElementException) as e:
        error_message = f"ERROR: Row not found or not clickable for {org.InstRegNr}, Exception: {str(e)}"
        error_log.append({'InstRegNr': org.InstRegNr, 'Organisation': organisation_name, 'Error': error_message})
    return result_df


def close_notifications_popup(browser):
    """
    Close the notification popups that may obstruct the automation process.

    Args:
        browser (webdriver.Chrome): The Selenium WebDriver instance.

    Returns:
        None
    """
    try:
        notfifications_close_button = WebDriverWait(browser, 5).until(
            EC.element_to_be_clickable((By.ID, "udbyder-close-button"))
        )
        notfifications_close_button.click()
    except TimeoutException:
        pass


def save_overview(result_df, base_dir, error_log):
    """
    Save the final DataFrame to an Excel file and configure data validation.

    Args:
        result_df (pd.DataFrame): DataFrame containing the processed results.
        base_dir (str): Base directory for all the Dataaftaler-processes.

    Returns:
        None
    """
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

            dv = DataValidation(type="list", formula1='"GODKEND, SLET, VENT"')
            dv.error_title = 'Invalid input'
            dv.error_message = 'Please select a value from the dropdown list'
            worksheet.add_data_validation(dv)
            for row in range(2, worksheet.max_row + 1):
                dv.add(worksheet[f'S{row}'])
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column].width = adjusted_width

    # Save Error Log
    if error_log:
        error_log_df = pd.DataFrame(error_log)
        error_log_filename = "Error_Log_" + datetime.now().strftime('%d%m%Y') + ".xlsx"
        error_log_path = os.path.join(output_dir, error_log_filename)
        error_log_df.to_excel(error_log_path, index=False, sheet_name='Errors')


def main(base_dir, connection_string):
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
        processed_instregnr = set()

        print("Processing institutioner tab...")
        for org in table_institution:
            result_df = process_organisation(browser, org, "Institutioner", base_dir, result_df, error_log)
            processed_instregnr.add(org.InstRegNr)
        
        print("Processing dagtilbud tab...")
        for org in table_dagtilbud:
            result_df = process_organisation(browser, org, "Dagtilbud", base_dir, result_df, error_log)
            processed_instregnr.add(org.InstRegNr)

        # Verify if all expected InstRegNr have been processed
        missing_instregnr = expected_instregnr - processed_instregnr
        if missing_instregnr:
            error_message = f"ERROR: The following InstRegNr were expected but not processed: {', '.join(missing_instregnr)}"
            print(error_message)
            for instregnr in missing_instregnr:
                error_log.append({'InstRegNr': instregnr, 'Organisation': 'Unknown', 'Error': 'File not downloaded or processed'})

    finally:
        browser.quit()
        save_overview(result_df, base_dir, error_log)  # Save the final overview and error log
