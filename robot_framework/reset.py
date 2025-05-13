"""This module handles resetting the state of the computer so the robot can work with a clean slate."""

import sys
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses.queue_handling import get_base_cookies, get_browser_cookie
from robot_framework.subprocesses.overview_creation import switch_to_new_tab
from robot_framework.exceptions import ResponseError


def open_stil_connection():
    """Opens STIL, waiting for user to log in."""
    browser = webdriver.Chrome()
    browser.maximize_window()
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

    return browser


def reset(orchestrator_connection: OrchestratorConnection) -> None:
    """Clean up, close/kill all programs and start them again. """
    orchestrator_connection.log_trace("Resetting.")
    clean_up(orchestrator_connection)
    close_all(orchestrator_connection)
    kill_all(orchestrator_connection)
    open_all(orchestrator_connection)


def clean_up(orchestrator_connection: OrchestratorConnection) -> None:
    """Do any cleanup needed to leave a blank slate."""
    orchestrator_connection.log_trace("Doing cleanup.")
    # Cleanup process arguments
    oc_args = json.loads(orchestrator_connection.process_arguments)
    oc_args.pop("runtime_args", None)


def close_all(orchestrator_connection: OrchestratorConnection) -> None:
    """Gracefully close all applications used by the robot."""
    orchestrator_connection.log_trace("Closing all applications.")
    if hasattr(orchestrator_connection, 'browser'):
        orchestrator_connection.browser.quit()
        orchestrator_connection.log_trace("Browser closed")


def kill_all(orchestrator_connection: OrchestratorConnection) -> None:
    """Forcefully close all applications used by the robot."""
    orchestrator_connection.log_trace("Killing all applications.")


def open_all(orchestrator_connection: OrchestratorConnection) -> None:
    """Open all programs used by the robot."""
    orchestrator_connection.log_trace("Opening all applications.")
    browser = open_stil_connection()
    orchestrator_connection.browser = browser
    # Get auth cookies from main page with list of institutioner
    base_cookie, x_xsrf_token = get_base_cookies(browser)
    cookie_inst_list = get_browser_cookie("AuthTokenTilslutning", browser)
    # Get list of organisations, and load payloads for request posts into dict
    resp_inst_list = requests.get(
        "https://tilslutning.stil.dk/tilslutningBE/organisationer/institutioner",
        headers={"Cookie": f"{base_cookie};{cookie_inst_list}"},
        timeout=10
    )
    resp_dag_list = requests.get(
        "https://tilslutning.stil.dk/tilslutningBE/organisationer/dagtilbud",
        headers={"Cookie": f"{base_cookie};{cookie_inst_list}"},
        timeout=10
    )
    # convert responses to dicts of payloads
    if not (resp_inst_list.status_code == 200 and resp_dag_list.status_code == 200):
        raise ResponseError(f"Error while fetching institution lists: {resp_inst_list = }; {resp_dag_list = }")

    inst_json = json.loads(resp_inst_list.text)
    inst_payload_dict = {org["kode"]: org for org in inst_json["organisationer"]}
    dag_json = json.loads(resp_dag_list.text)
    dag_payload_dict = {org["kode"]: org for org in dag_json["organisationer"]}
    # store in process arguments
    runtime_args = {
        "base_cookie": base_cookie,
        "x-xsrf-token": x_xsrf_token,
        "cookie_inst_list": cookie_inst_list,
        "inst_payload_dict": inst_payload_dict,
        "dag_payload_dict": dag_payload_dict
    }
    oc_args = json.loads(orchestrator_connection.process_arguments)
    oc_args["runtime_args"] = runtime_args
    orchestrator_connection.process_arguments = json.dumps(oc_args)
