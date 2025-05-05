"""This module contains the queue handling process of the robot."""
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
from OpenOrchestrator.database.queues import QueueStatus
from .overview_creation import open_stil_connection

MAX_RETRIES = 3
RETRY_DELAY = 5
DEFAULT_WAIT_TIME = 30


def process_queue_elements(queue_elements, orchestrator_connection):
    """Process each queue element by grouping and handling them based on their reference type."""
    browser = webdriver.Chrome()
    try:
        open_stil_connection(browser)
        grouped_elements = group_elements_by_instregnr(queue_elements)

        for instregnr, elements in grouped_elements.items():
            handle_elements_for_instregnr(browser, instregnr, elements, orchestrator_connection)
    except (Exception) as e:
        print(f"Encountered an error: {e}")
    finally:
        browser.quit()


def wait_for_react_app(browser, timeout=10):
    try:
        # Vent på at React-appen er fuldt indlæst
        WebDriverWait(browser, timeout).until(
            lambda driver: driver.execute_script(
                "return window.React && document.getElementById('react').children.length > 0"
            )
        )
        return True
    except Exception as e:
        print(f"React app load error: {e}")
        return False


def click_element_with_retries(
    browser,
    by,
    value,
    retries=4,
    react_wait=True
):
    for attempt in range(retries):
        try:
            # Ekstra React-ventetid hvis aktiveret
            if react_wait:
                wait_for_react_app(browser, timeout=2)

            element = WebDriverWait(browser, 5).until(
                EC.element_to_be_clickable((by, value))
            )

            browser.execute_script("arguments[0].scrollIntoView(true);", element)

            try:
                element.click()
            except Exception:
                # Fallback til JavaScript click
                browser.execute_script("arguments[0].click();", element)

            print(f"Successfully clicked element '{value}' on attempt {attempt + 1}")
            return True

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            browser.refresh()
            time.sleep(2)

    print(f"Failed to click element '{value}' after {retries} attempts")
    return False


def group_elements_by_instregnr(queue_elements):
    """Organize queue elements into groups based on their institution registration number ('instregnr')."""
    grouped_elements = {}
    for element in queue_elements:
        element_data = json.loads(element.data)
        instregnr = element_data['Instregnr']
        grouped_elements.setdefault(instregnr, []).append(element)

    # Print the total amount of element
    print(f"Total amount of elements: {len(queue_elements)}")
    return grouped_elements


def handle_elements_for_instregnr(browser, instregnr, elements, orchestrator_connection):
    """Process all queue elements for a specific institution registration number."""
    element_data = json.loads(elements[0].data)  # Assume all elements have the same organization
    org = element_data['Organisation']

    orchestrator_connection.log_trace(f"Processing {len(elements)} queue elements for {instregnr} ({org})")

    for _ in range(MAX_RETRIES):
        try:
            enter_organisation(browser, org, instregnr)
            break
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error navigating to data access administration for {instregnr}: {e}. Retrying...")
            orchestrator_connection.log_error(f"Error navigating to data access administration for {instregnr}: {e}. Retrying...")
            time.sleep(RETRY_DELAY)
    else:
        # Mark elements as failed after max retries
        for element in elements:
            orchestrator_connection.set_queue_element_status(element.id, QueueStatus.FAILED, "Failed entering Data Access Administration")
        orchestrator_connection.log_error(f"Failed after {MAX_RETRIES} retries: Error navigating to data access administration. All elements with Instregnr: {instregnr} set to failed.")
        return

    # Process each individual element for the institution
    for element in elements:
        process_element(browser, element, orchestrator_connection)


def process_element(browser, queue_element, orchestrator_connection):
    """Handle an individual queue element with retry logic."""
    element_data = json.loads(queue_element.data)
    ref = queue_element.reference

    orchestrator_connection.log_trace(f"Processing element {queue_element.id} with reference '{ref}'")

    for _ in range(MAX_RETRIES):
        orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.IN_PROGRESS)
        try:
            success, message = perform_data_access(browser, element_data, ref, queue_element)

            if success:
                orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.DONE, message)
                orchestrator_connection.log_trace(f"Element {queue_element.id} processed successfully: {message}")
                break

            orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.FAILED, message)
            orchestrator_connection.log_error(f"Failed to process element {queue_element.id}: {message}. Retrying...")

        except (TimeoutException, NoSuchElementException) as e:
            orchestrator_connection.log_error(f"Error processing element {queue_element.id}: {e}. Retrying...")
            print(f"Error processing element {queue_element.id}: {e}. Retrying...")
            time.sleep(RETRY_DELAY)
    else:
        orchestrator_connection.log_error(f"Maximum retries reached for element {queue_element.id} - Failed to process element")
        orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.FAILED, "Maximum retries reached - Failed to process element")


def click_checkbox_if_not_checked(browser, checkbox_id):
    """Click a checkbox if it is not already checked."""
    # Wait until the checkbox is present in the DOM
    checkbox = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.ID, checkbox_id))
    )

    # Check if the checkbox is already checked
    if not checkbox.is_selected():
        checkbox.click()  # Click the checkbox to check it


def perform_data_access(browser, element_data, ref, queue_element):  # pylint: disable=too-many-return-statements
    """Perform data access operations like approving, awaiting, or deleting an agreement."""
    system_name = element_data['systemNavn']
    service_name = element_data['serviceNavn']
    status = element_data['status']
    time.sleep(2)  # Add sleep to account for possible delays

    click_checkbox_if_not_checked(browser, 'visSlettede')
    click_checkbox_if_not_checked(browser, 'visPassive')

    # Wait until the table container is fully loaded
    table = WebDriverWait(browser, DEFAULT_WAIT_TIME).until(
        EC.presence_of_element_located((By.XPATH, "//table[@class='stil-tabel']"))
    )

    # Find all rows across the entire container
    all_rows = table.find_elements(By.XPATH, ".//tbody/tr")  # Relative path to the tbody

    # To track if agreement is found
    agreement_found = False

    for row in all_rows:
        click_checkbox_if_not_checked(browser, 'visSlettede')
        click_checkbox_if_not_checked(browser, 'visPassive')

        data_cells = row.find_elements(By.TAG_NAME, "td")
        if not data_cells:
            continue  # Skip to the next row if no <td> is found

        row_texts = []
        for cell in data_cells:
            span_elements = cell.find_elements(By.TAG_NAME, "span")  # Find <span> in each <td>
            for span in span_elements:
                row_texts.append(span.text.strip())  # Append the text from the <span>

        print(f"Checking row: {row_texts}")

        # Check if both system_name and service_name are present in row_texts
        if (system_name.strip() in [text.strip() for text in row_texts] and service_name.strip() in [text.strip() for text in row_texts]):

            browser.execute_script("arguments[0].scrollIntoView(true);", row)
            print(f"Found agreement for {system_name} - {service_name}")
            browser.execute_script("arguments[0].style.backgroundColor = 'yellow'", row)  # Highlight the row for visibility

            # Additional status checks and actions
            if ref.startswith('Godkend') and status == 'VENTER':
                print(f"Element expected pre-status: {status}. Getting ready to change status to 'GODKENDT'...")
                pre_status = check_status_change(system_name, service_name, 'GODKENDT', browser, row_texts)
                if pre_status:
                    print("Agreement already approved")
                    return True, "Agreement already approved"
                print("Proceeding to change agreement status to 'GODKENDT'...")
                change_status(browser, queue_element, row)
                time.sleep(2)  # Add sleep to account for possible delays
                browser.switch_to.default_content()
                browser.execute_script("window.scrollTo(0, 0)")
                browser.switch_to.default_content()
                confirmation = WebDriverWait(browser, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Status for dataadgang er opdateret.')]"))
                )
                if confirmation:
                    print("Agreement succesfully changed to 'GODKENDT'")
                    return True, "Agreement status changed to 'GODKENDT'"

            if ref.startswith('Vent') and status == 'GODKENDT':
                print(f"Element expected pre-status: {status}. Getting ready to change status to 'VENTER'...")
                pre_status = check_status_change(system_name, service_name, 'VENTER', browser, row_texts)
                if pre_status:
                    print("Agreement already awaiting")
                    return True, "Agreement already awaiting"
                print("Proceeding to change agreement status to 'VENTER'...")
                change_status(browser, queue_element, row)
                time.sleep(2)  # Add sleep to account for possible delays
                browser.switch_to.default_content()
                browser.execute_script("window.scrollTo(0, 0)")
                browser.switch_to.default_content()
                confirmation = WebDriverWait(browser, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Status for dataadgang er opdateret.')]"))
                )
                if confirmation:
                    print("Agreement succesfully changed to 'VENTER'")
                    return True, "Agreement status changed to 'VENTER'"

            if ref.startswith('Slet') and status != 'SLETTET':
                print(f"Element expected pre-status: {status}. Getting ready to delete agreement...")
                pre_status = check_status_change(system_name, service_name, 'SLETTET', browser, row_texts)
                if pre_status:
                    print("Agreement already deleted")
                    return True, "Agreement already deleted"
                print("Proceeding to delete agreement...")
                return delete_agreement(browser, queue_element, row)

            # Mark agreement found
            agreement_found = True

    if not agreement_found:
        print(f"Agreement not found for {system_name} - {service_name}")
        return False, "Agreement not found"

    return False, "Agreement not found or failed to update status"


def check_status_change(system_name, service_name, expected_status, browser, column_texts):
    """Helper to check if the status change was successful."""
    print("Checking agreement status...")
    retry_count = 0
    max_retries = MAX_RETRIES

    while retry_count < max_retries:
        try:
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'table.stil-tabel'))
            )
            if (system_name.strip() in [text.strip() for text in column_texts] and service_name.strip() in [text.strip() for text in column_texts] and expected_status in [text.strip() for text in column_texts]):
                return True
            return False
        except StaleElementReferenceException as e:
            print(f"Encountered a stale element exception: {e}. Retrying...")
            retry_count += 1
            time.sleep(RETRY_DELAY)  # Short delay before retrying
        except TimeoutException as e:
            print(f"Timeout while checking status change: {e}.")
            break
    return False


def change_status(browser, queue_element, row):
    """Click the status change button and change status based on the queue element's reference."""
    status_button = WebDriverWait(row, 10).until(
            EC.presence_of_element_located((By.XPATH, ".//img[@class='hand dataadgang-status-knap' and @title='Skift status']"))
        )
    print("Clicking status button...")
    browser.execute_script("arguments[0].style.backgroundColor = 'red'", status_button)  # Highlight the button for visibility

    status_button.click()

    if queue_element.reference.startswith('Vent'):
        print("Clicking Venter button")
        time.sleep(1)  # Add sleep to account for possible delays
        click_element_with_retries(browser, By.XPATH, '//button[text()="Til Venter"]')
        WebDriverWait(browser, 20).until(
            EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), 'Er du sikker på, at adgangens status skal ændres til VENTER')]"))
        )

    elif queue_element.reference.startswith('Godkend'):
        print("Clicking Godkendt button")
        time.sleep(1)
        click_element_with_retries(browser, By.XPATH, '//button[text()="Godkend"]')
        WebDriverWait(browser, 20).until(
            EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), 'Er du sikker på, at adgangens status skal ændres til GODKENDT')]"))
        )

    click_element_with_retries(browser, By.XPATH, '/html/body/div[4]/div/div/div/div/button[2]')
    time.sleep(2)


def delete_agreement(browser, queue_element, row):
    """Delete an agreement if it meets the criteria."""
    try:
        delete_button = row.find_element(By.XPATH, './/img[@src="img/ic_delete_24px.svg" and @title="Slet dataadgang"]')
        browser.execute_script("arguments[0].style.backgroundColor = 'red'", delete_button)  # Highlight the button for visibility

        delete_button.click()
        time.sleep(2)  # Add sleep to account for possible delays
        print("Clicking Slet button")
        click_element_with_retries(browser, By.XPATH, '//button[text()="Slet"]')
        time.sleep(2)
        browser.switch_to.default_content()
        browser.execute_script("window.scrollTo(0, 0)")
        browser.switch_to.default_content()

        print("Checking status change after deletion...")
        confirmation = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'er slettet')]"))
        )

        if confirmation:
            print("Agreement successfully deleted")
            return True, "Agreement deleted successfully"

    except TimeoutException:
        print(f"Failed to delete agreement for queue element {queue_element.id}")
    return False, "Failed to delete agreement"


def enter_dataadministration(browser):
    """Handles the notification popup and clicks the necessary elements."""
    try:
        notifications_close_button = WebDriverWait(browser, 2).until(
            EC.element_to_be_clickable((By.ID, "udbyder-close-button"))
        )
        if notifications_close_button:
            close_notifications_popup(browser)
            return True

        if not browser.execute_script("return document.readyState") == "complete":
            browser.refresh()
            time.sleep(2)

    except TimeoutException:
        pass
    return click_element_with_retries(browser, By.XPATH, "/html/body/div[1]/div/div[2]/div[2]/div/div[2]/div/h3/a")


def enter_organisation(browser, org, instregnr):
    """Navigate to the organization and click the necessary elements."""
    for attempt in range(MAX_RETRIES):
        try:
            print(f"Processing organisation: {org}, InstRegNr: {instregnr}")
            browser.get('https://tilslutning.stil.dk/tilslutning?select-organisation=true')
            browser.refresh()

            if org == "Dagtilbud":
                print("Switching to Dagtilbud tab...")
                dagtilbud_button = WebDriverWait(browser, 20).until(
                    EC.element_to_be_clickable((By.ID, "dagtilbud-tab-button"))
                )
                dagtilbud_button.click()

            row = WebDriverWait(browser, 20).until(
                EC.visibility_of_element_located((By.XPATH, f"//*[contains(text(), '{instregnr}')]"))
            )
            browser.execute_script("arguments[0].scrollIntoView(true);", row)
            click_element_with_retries(browser, By.XPATH, f"//*[contains(text(), '{instregnr}')]")
            print(f"Clicked row for {instregnr}...")

            if enter_dataadministration(browser):
                return
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error finding organisation {org}, InstRegNr: {instregnr} on attempt {attempt + 1}. Exception: {e}")
            time.sleep(RETRY_DELAY)

    print(f"Couldn't find organisation {org}, InstRegNr: {instregnr} after {MAX_RETRIES} attempts.")


def close_notifications_popup(browser):
    """Close any notification popups that may obstruct the automation process."""
    try:
        WebDriverWait(browser, 5).until(
            EC.element_to_be_clickable((By.ID, "udbyder-close-button"))
        ).click()
    except TimeoutException:
        print("No notification popup found or close button not clickable.")
