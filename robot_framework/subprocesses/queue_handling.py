""" This module handle the queue elements for changing their status in STIL."""

from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from OpenOrchestrator.database.queues import QueueStatus
import json


def run_queue_handling(queue_elements, orchestrator_connection):
    """
    Handle the queue elements. Process each element based on its reference type: Godkend, Slet, or Vent.

    Args:
        queue_elements (list of dict): The queue elements to handle.
        orchestrator_connection: The connection object to update the queue status.

    Returns:
        None
    """
    browser = webdriver.Chrome()
    try:
        open_stil_connection(browser)
        
        for queue_element in queue_elements:
            process_queue_element(browser, queue_element, orchestrator_connection)
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        browser.quit()

def process_queue_element(browser, queue_element, orchestrator_connection):
    """Process an individual queue element."""

    element_data = json.loads(queue_element.data)
    ref = queue_element.reference

    orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.IN_PROGRESS)

    try:
        navigate_to_data_access_admin(browser, element_data['Organisation'], element_data['Instregnr'])
        handle_data_access(browser, element_data, ref, orchestrator_connection, queue_element)
    except (TimeoutException, NoSuchElementException) as e:
        print(f"Error processing element {queue_element.id}: {str(e)}")


def navigate_to_data_access_admin(browser, org, instregnr):
    """Navigate to the 'Dataadgangadministration' section for the given organization and institution number."""

    browser.get("https://tilslutning.stil.dk/tilslutning?select-organisation=true")
    
    if org == 'Dagtilbud':
        WebDriverWait(browser, 20).until(
            EC.element_to_be_clickable((By.ID, "dagtilbud-tab-button"))
        ).click()

    WebDriverWait(browser, 20).until(
        EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{instregnr}')]"))
    ).click()

    close_notifications_popup(browser)
    
    WebDriverWait(browser, 20).until(
        EC.element_to_be_clickable((By.LINK_TEXT, "Dataadgangadministration"))
    ).click()


def handle_data_access(browser, element_data, ref, orchestrator_connection, queue_element):
    """Handle data access operations like approving, setting to Awaits, or deleting an agreement."""

    system_navn = element_data['systemNavn']
    service_navn = element_data['serviceNavn']
    status = element_data['status']

    table = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'table.stil-tabel'))
    )

    rows = table.find_elements(By.TAG_NAME, 'tr')
    for row in rows:
        columns = row.find_elements(By.TAG_NAME, 'td')
        column_texts = [col.text for col in columns]

        if system_navn in column_texts and service_navn in column_texts and status in column_texts:
            if ref.startswith('Godkend') and status == 'VENTER':
                change_status(browser, "Sætter status til Godkendt", "GODKENDT", orchestrator_connection, queue_element, "Aftale godkendt.")
            elif ref.startswith('Vent') and status == 'GODKENDT':
                change_status(browser, "Sætter status til Venter", "VENTER", orchestrator_connection, queue_element, "Aftale sat til venter.")
            elif ref.startswith('Slet') and status != 'SLETTET':
                delete_agreement(browser, system_navn, service_navn, status, orchestrator_connection, queue_element)
            break


def change_status(browser, action_title, expected_status, orchestrator_connection, queue_element, success_message):
    """Change the status (Godkend or Venter) of an agreement."""
    try:
        WebDriverWait(browser, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, f'button.hand.margleft10.stil-primary-button.button[title="{action_title}"]'))
        ).click()

        table = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'table.stil-tabel'))
        )

        rows = table.find_elements(By.TAG_NAME, 'tr')
        for row in rows:
            columns = row.find_elements(By.TAG_NAME, 'td')
            if expected_status in [col.text for col in columns]:
                orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.DONE, message=success_message)
                break
    except TimeoutException:
        print(f"Failed to change status for queue element {queue_element.id}")


def delete_agreement(browser, system_navn, service_navn, status, orchestrator_connection, queue_element):
    """Delete an agreement."""
    try:
        WebDriverWait(browser, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'img.tableImg.hand.dataadgang-slet[title="Slet dataadgang"]'))
        ).click()

        WebDriverWait(browser, 50).until(
            EC.element_to_be_clickable((By.XPATH, "//div[@class='react-confirm-alert-button-group']/button[text()='Slet']"))
        ).click()

        table = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'table.stil-tabel'))
        )
        rows = table.find_elements(By.TAG_NAME, 'tr')
        for row in rows:
            columns = row.find_elements(By.TAG_NAME, 'td')
            column_texts = [col.text for col in columns]
            if system_navn not in column_texts and service_navn not in column_texts and status not in column_texts:
                orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.DONE, message="Aftale slettet.")

    except TimeoutException:
        print(f"Failed to delete agreement for queue element {queue_element.id}")


def close_notifications_popup(browser):
    """Close the notification popups that may obstruct the automation process."""
    try:
        WebDriverWait(browser, 5).until(
            EC.element_to_be_clickable((By.ID, "udbyder-close-button"))
        ).click()
    except TimeoutException:
        print("No notification popup found or close button not clickable.")


def open_stil_connection(browser):
    """Opens STIL and waits for user to log in."""

    browser.get("https://tilslutning.stil.dk/tilslutning/login")
    try:
        WebDriverWait(browser, 60).until(EC.presence_of_element_located((By.ID, "LoginMenuItem_2"))).click()
        switch_to_new_tab(browser)
        WebDriverWait(browser, 60).until(
            EC.presence_of_element_located((By.ID, "ddlLocalIdPOrganization-input"))
        ).send_keys("Aarhus Kommune, 55133018, Aarhus Kommune")

        browser.find_element(By.ID, "ddlLocalIdPOrganization-input").click()
        browser.find_element(By.ID, "btnSubmit").click()

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
