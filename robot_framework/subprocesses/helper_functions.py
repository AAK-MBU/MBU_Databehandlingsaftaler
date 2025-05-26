"""Helper functions"""
import json
import sys
from requests import Session
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueElement
from robot_framework.exceptions import ResponseError
from robot_framework.config import REQUEST_TIMEOUT


def flatten_dict(d, parent_key='', sep='_'):
    """
    Flatten a nested dictionary.

    Args:
        d (dict): The dictionary to flatten.
        parent_key (str): The base key string for nested keys.
        sep (str): Separator between keys.

    Returns:
        dict: A flattened dictionary.
    """
    items = {}
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def get_org_dict(session: Session):
    """Get dict of all organisations"""
    inst_dict = get_inst_dict(session)
    dag_dict = get_dag_dict(session)
    org_dict = inst_dict | dag_dict

    return org_dict


def get_inst_dict(session: Session):
    """Get dict of institutions"""
    resp_inst_list = session.get(
        "https://tilslutning.stil.dk/tilslutningBE/organisationer",
        timeout=10
    )

    inst_json = json.loads(resp_inst_list.text)
    inst_payload_dict = {org["kode"]: org for org in inst_json["institutioner"]}

    return inst_payload_dict


def get_dag_dict(session: Session):
    """Get dict of dagtilbud"""
    resp_dag_list = session.get(
        "https://tilslutning.stil.dk/tilslutningBE/organisationer",
        timeout=10
    )

    # convert response to dicts of payloads
    if not (resp_dag_list.status_code == 200):
        raise ResponseError(f"Error while fetching institution lists: {resp_dag_list = }")

    dag_json = json.loads(resp_dag_list.text)
    dag_payload_dict = {org["kode"]: org for org in dag_json["dagtilbud"]}

    return dag_payload_dict


def switch_to_new_tab(browser: webdriver.Chrome):
    '''Switch to new tab.'''
    if len(browser.window_handles) > 1:
        browser.switch_to.window(browser.window_handles[1])


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


def get_browser_cookie(cookie_name, browser: webdriver.Chrome):
    """Retrieves base cookie from webdriver.Chrome instance"""
    cookie = None
    for c in browser.get_cookies():
        if c['name'] == cookie_name:
            cookie = f"{c['name']}={c['value']}"
    return cookie


def get_base_cookies(browser):
    """Retrieves base cookies for use in all calls"""
    base_cookie = ''
    for cookie_name in ["persistence-cookie", "SESSION", "XSRF-TOKEN"]:
        base_cookie += (get_browser_cookie(cookie_name, browser)+";")
    x_xsrf_token = get_browser_cookie("XSRF-TOKEN", browser).split("=", maxsplit=1)[-1]
    return base_cookie, x_xsrf_token


def get_request_cookie(cookie_name, response):
    """Get cookie from request.response instance"""
    cookie = None
    for c in response.cookies:
        if c.name == cookie_name:
            cookie = f"{c.name}={c.value};"
    return cookie


def get_payload(org_num: str, runtime_args: dict):
    """Retrieves needed payload from runtime args based on organisation type and number"""
    org_dict = runtime_args.get("org_dict", None)
    if org_dict is None:
        raise ValueError(f"No organisation dictionary in runtime arguments: {runtime_args = }")
    payload = org_dict.get(org_num, None)
    return payload


def get_org(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement | dict, runtime_args: dict, session: Session):
    """Accesses organisation related to queue element"""
    queue_data = json.loads(queue_element.data) if isinstance(queue_element, QueueElement) else queue_element
    org_type = queue_data["Organisation"]
    org_num = queue_data["Instregnr"]

    payload = get_payload(org_num, runtime_args)

    resp_get_org = session.post(
        "https://tilslutning.stil.dk/tilslutningBE/active-organisation",
        headers={
            # "Cookie": f"{runtime_args['base_cookie']};{runtime_args['cookie_inst_list']}",
            # "x-xsrf-token": runtime_args['x-xsrf-token'],
            "accept": "application/json",
            "content-type": "application/json",
            "Accept": "*/*"
        },
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT
    )
    if not resp_get_org.status_code == 200:
        orchestrator_connection.log_error(f"Error fetching organisation: {org_type = }, {org_num = }")
        raise ResponseError(resp_get_org)

    return resp_get_org


def get_data(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement | dict, session: Session):
    """Retrieves data for organization"""
    queue_data = json.loads(queue_element.data) if isinstance(queue_element, QueueElement) else queue_element
    org_type = queue_data["Organisation"]
    org_num = queue_data["Instregnr"]

    resp_get_data = session.get(
            "https://tilslutning.stil.dk/dataadgangadmBE/api/adgang/hent",
            timeout=REQUEST_TIMEOUT
        )
    if not resp_get_data.status_code == 200:
        orchestrator_connection.log_error(f"Error while accessing data for organization: {org_type = }, {org_num = }")
        raise ResponseError(resp_get_data)

    data_access_json = json.loads(resp_get_data.text)
    agreements_dict = {f"{agr['udbyderSystemOgUdbyder']['navn']}_{agr['stilService']['servicenavn']}_{agr['aktuelStatus']}": agr for agr in data_access_json if agr['stilService'] is not None}
    return agreements_dict


def delete_agreement(orchestrator_connection: OrchestratorConnection, agreement: dict, session: Session):
    """Deletes inputted agreement"""
    agreement_id = agreement["id"]
    delete_resp = session.delete(
        f"https://tilslutning.stil.dk/dataadgangadmBE/api/adgang/slet/{agreement_id}",
        timeout=REQUEST_TIMEOUT
    )
    if not delete_resp.status_code == 200:
        orchestrator_connection.log_error(f"Error when deleting agreement: {delete_resp}")
        raise ResponseError(delete_resp)
    return delete_resp


def change_status(orchestrator_connection: OrchestratorConnection, reference: str, agreement: dict, session: Session):
    """Changes status for inputted agreement based on reference"""

    set_status = get_status(reference)

    if set_status is None:
        raise ValueError(f"reference status: {reference.split('_')[0]} does not match any of 'Godkend', 'Vent', or 'Slet'")

    orchestrator_connection.log_trace(f"Setting status from {agreement['aktuelStatus']} to {set_status}")

    payload = {"aftaleid": agreement['id'], "status": set_status, "kommentar": None}
    payload = json.dumps(payload)

    status_resp = session.post(
        "https://tilslutning.stil.dk/dataadgangadmBE/api/adgang/setStatus",
        headers={
            "accept": "application/json",  # maybe this in session header too?
            "content-type": "application/json",
            "Accept": "*/*"
        },
        data=payload,
        timeout=REQUEST_TIMEOUT
    )

    if not status_resp.status_code == 200:
        orchestrator_connection.log_error("Error while changing status")
        raise ResponseError(status_resp)

    return status_resp


def get_status(reference):
    """Converts reference to status used in API calls"""
    set_status_dict = {
        'Godkend': 'GODKENDT',
        'Vent': 'VENTER',
        'Slet': 'SLETTET',
    }

    set_status = set_status_dict.get(reference.split('_')[0], None)

    return set_status
