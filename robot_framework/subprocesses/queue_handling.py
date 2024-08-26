""" This module handle the queue elements for changing their status in STIL."""

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


def process_queue_elements(queue_elements, orchestrator_connection):
    """Process each queue element by grouping them and handling them based on their reference type."""
    browser = webdriver.Chrome()
    try:
        open_stil_connection(browser)
        grouped_elements = group_elements_by_instregnr(queue_elements)

        for instregnr, elements in grouped_elements.items():
            handle_elements_for_instregnr(browser, instregnr, elements, orchestrator_connection)
    except (TimeoutException, NoSuchElementException) as e:
        print(f"Encountered an error: {e}")
    finally:
        browser.quit()


def click_element_with_retries(browser, by, value, max_retries=MAX_RETRIES):
    """Attempt to click an element multiple times, handling common click-related exceptions."""
    for attempt in range(max_retries):
        try:
            element = WebDriverWait(browser, 2).until(
                EC.visibility_of_element_located((by, value))
            )
            element.click()
            print(f"Clicked element '{value}' successfully on attempt {attempt + 1}")
            return True
        except (TimeoutException, ElementClickInterceptedException, StaleElementReferenceException) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(1)
    print(f"Failed to click element '{value}' after {max_retries} attempts")
    return False


def group_elements_by_instregnr(queue_elements):
    """Organize queue elements into groups based on their institution registration number ('instregnr')."""
    grouped_elements = {}
    for element in queue_elements:
        element_data = json.loads(element.data)
        instregnr = element_data['Instregnr']
        if instregnr not in grouped_elements:
            grouped_elements[instregnr] = []
        grouped_elements[instregnr].append(element)
    return grouped_elements


def handle_elements_for_instregnr(browser, instregnr, elements, orchestrator_connection):
    """Process all queue elements for a specific institution registration number."""
    element_data = json.loads(elements[0].data)  # Assume all elements have the same organization
    org = element_data['Organisation']

    for _ in range(MAX_RETRIES):
        try:
            navigate_to_data_access_admin(browser, org, instregnr)
            for element in elements:
                process_element(browser, element, orchestrator_connection)
            break
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error processing elements for {instregnr}: {e}. Retrying...")
            time.sleep(RETRY_DELAY)
    else:
        for element in elements:
            orchestrator_connection.set_queue_element_status(element.id, QueueStatus.FAILED)


def process_element(browser, queue_element, orchestrator_connection):
    """Handle an individual queue element with retry logic."""
    element_data = json.loads(queue_element.data)
    ref = queue_element.reference

    orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.IN_PROGRESS)

    for _ in range(MAX_RETRIES):
        try:
            if perform_data_access(browser, element_data, ref, orchestrator_connection, queue_element):
                orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.DONE)
                break
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error processing element {queue_element.id}: {e}. Retrying...")
            time.sleep(RETRY_DELAY)
    else:
        orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.FAILED)


def perform_data_access(browser, element_data, ref, orchestrator_connection, queue_element):
    """Perform data access operations like approving, awaiting, or deleting an agreement."""
    system_name = element_data['systemNavn']
    service_name = element_data['serviceNavn']
    status = element_data['status']

    table = WebDriverWait(browser, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'table.stil-tabel'))
    )

    rows = table.find_elements(By.TAG_NAME, 'tr')
    for row in rows:
        columns = row.find_elements(By.TAG_NAME, 'td')
        column_texts = [col.text for col in columns]

        if system_name in column_texts and service_name in column_texts and status in column_texts:
            if ref.startswith('Godkend') and status == 'VENTER':
                change_status(browser, queue_element)
                time.sleep(2)  # Wait for status change to take effect
                if system_name in column_texts and service_name in column_texts:
                    if 'GODKENDT' not in column_texts:
                        return True

            elif ref.startswith('Vent') and status == 'GODKENDT':
                change_status(browser, queue_element)
                time.sleep(2)  # Wait for status change to take effect
                if system_name in column_texts and service_name in column_texts:
                    if 'VENTER' in column_texts:
                        return True

            elif ref.startswith('Slet') and status != 'SLETTET':
                return delete_agreement(browser, system_name, service_name, status, orchestrator_connection, queue_element)
            break
    return False


def change_status(browser, queue_element):
    """Click the status change button and change status based on the queue element's reference."""

    click_element_with_retries(browser, By.XPATH, '//img[@src="img/ic_apps_24px.svg" and contains(@class, "hand") and contains(@class, "dataadgang-status-knap") and @title="Skift status"]')

    if queue_element.reference.startswith('Vent'):
        print("Clicking Venter button")
        time.sleep(5)
        click_element_with_retries(browser, By.XPATH, '//button[@title="Sætter status til Venter" and contains(@class, "hand") and contains(@class, "margleft10") and contains(@class, "stil-primary-button") and contains(@class, "button")]')
    elif queue_element.reference.startswith('Godkend'):
        print("Clicking Godkendt button")
        time.sleep(5)
        click_element_with_retries(browser, By.XPATH, '//button[@title="Sætter status til Godkendt" and contains(@class, "hand") and contains(@class, "margleft10") and contains(@class, "stil-primary-button") and contains(@class, "button")]')


def delete_agreement(browser, system_name, service_name, status, orchestrator_connection, queue_element):
    """Delete an agreement if it meets the criteria."""
    try:
        click_element_with_retries(browser, By.XPATH, '//img[@src="img/ic_delete_24px.svg" and @title="Slet dataadgang" and contains(@class, "tableImg") and contains(@class, "hand") and contains(@class, "dataadgang-slet")]')
        print("Clicked Slet button")
        time.sleep(5)
        click_element_with_retries(browser, By.XPATH, '//button[text()="Slet"]')

        table = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'table.stil-tabel'))
        )
        rows = table.find_elements(By.TAG_NAME, 'tr')
        for row in rows:
            columns = row.find_elements(By.TAG_NAME, 'td')
            column_texts = [col.text for col in columns]

        if system_name not in column_texts and service_name not in column_texts and status not in column_texts:
            orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.DONE, message="Agreement deleted.")
            return True
    except TimeoutException:
        print(f"Failed to delete agreement for queue element {queue_element.id}")
    return False


def navigate_to_data_access_admin(browser, org, instregnr):
    """Navigate to the Data Access Administration section for a given organization and institution number."""
    browser.get("https://tilslutning.stil.dk/tilslutning?select-organisation=true")

    if org == 'Dagtilbud':
        WebDriverWait(browser, 20).until(
            EC.element_to_be_clickable((By.ID, "dagtilbud-tab-button"))
        ).click()

    WebDriverWait(browser, 20).until(
        EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{instregnr}')]"))
    ).click()

    close_notifications_popup(browser)
    click_element_with_retries(browser, By.XPATH, "/html/body/div[1]/div/div[2]/div[2]/div/div[2]/div/h3/a")


def close_notifications_popup(browser):
    """Close any notification popups that may obstruct the automation process."""
    try:
        WebDriverWait(browser, 5).until(
            EC.element_to_be_clickable((By.ID, "udbyder-close-button"))
        ).click()
    except TimeoutException:
        print("No notification popup found or close button not clickable.")


def switch_to_new_tab(browser):
    """Switch to the newly opened tab in the browser."""
    if len(browser.window_handles) > 1:
        browser.switch_to.window(browser.window_handles[1])
