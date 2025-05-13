"""This module contains the queue handling process of the robot."""
import json
import requests
from selenium import webdriver
from OpenOrchestrator.database.queues import QueueElement
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.exceptions import ResponseError, BusinessError
from robot_framework.config import REQUEST_TIMEOUT


class ReactAppLoadError(Exception):
    """Custom exception for react load errors"""


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
    x_xsrf_token = get_browser_cookie("XSRF-TOKEN", browser).split("=")[-1]
    return base_cookie, x_xsrf_token


def get_request_cookie(cookie_name, response):
    """Get cookie from request.response instance"""
    cookie = None
    for c in response.cookies:
        if c.name == cookie_name:
            cookie = f"{c.name}={c.value};"
    return cookie


def get_payload(org_type: str, org_num: str, runtime_args: dict):
    """Retrieves needed payload from runtime args based on organisation type and number"""
    payload = None
    if org_type == "Institutioner":
        payload = runtime_args["inst_payload_dict"][org_num]
    elif org_type == "Dagtilbud":
        payload = runtime_args["dag_payload_dict"][org_num]
    else:
        raise ValueError(f"org_type should be 'Institutioner' or 'Dagtilbud' but is {org_type}")
    return payload


def get_org(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement, runtime_args: dict):
    """Accesses organisation related to queue element"""
    queue_data = json.loads(queue_element.data)
    org_type = queue_data["Organisation"]
    org_num = queue_data["Instregnr"]

    payload = get_payload(org_type, org_num, runtime_args)

    resp_get_org = requests.post(
        "https://tilslutning.stil.dk/tilslutningBE/active-organisation",
        headers={
            "Cookie": f"{runtime_args['base_cookie']};{runtime_args['cookie_inst_list']}",
            "x-xsrf-token": runtime_args['x-xsrf-token'],
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


def get_data(orchestrator_connection, queue_element, runtime_args, org_cookie):
    """Retrieves data for organization"""
    queue_data = json.loads(queue_element.data)
    org_type = queue_data["Organisation"]
    org_num = queue_data["Instregnr"]

    resp_get_data = requests.get(
            "https://tilslutning.stil.dk/dataadgangadmBE/api/adgang/hent",
            headers={"Cookie": f"{runtime_args['base_cookie']};{org_cookie}"},
            timeout=REQUEST_TIMEOUT
        )
    if not resp_get_data.status_code == 200:
        orchestrator_connection.log_error(f"Error while accessing data for organization: {org_type = }, {org_num = }")
        raise ResponseError(resp_get_data)

    data_access_json = json.loads(resp_get_data.text)
    agreements_dict = {f"{agr['udbyderSystemOgUdbyder']['navn']}_{agr['stilService']['servicenavn']}_{agr['aktuelStatus']}": agr for agr in data_access_json if agr['stilService'] is not None}
    return agreements_dict


def delete_agreement(orchestrator_connection: OrchestratorConnection, agreement: dict, runtime_args: dict, org_cookie: str):
    """Deletes inputted agreement"""
    agreement_id = agreement["id"]
    delete_resp = requests.delete(
        f"https://tilslutning.stil.dk/dataadgangadmBE/api/adgang/slet/{agreement_id}",
        headers={
            "Cookie": f"{runtime_args['base_cookie']};{org_cookie}",
            "x-xsrf-token": runtime_args['x-xsrf-token'],
        },
        timeout=REQUEST_TIMEOUT
    )
    if not delete_resp.status_code == 200:
        orchestrator_connection.log_error(f"Error when deleting agreement: {delete_resp}")
        raise ResponseError(delete_resp)
    return delete_resp


def change_status(orchestrator_connection: OrchestratorConnection, reference: str, agreement: dict, runtime_args: dict, org_cookie: str):
    """Changes status for inputted agreement based on reference"""

    set_status = get_status(reference)

    if set_status is None:
        raise ValueError(f"reference status: {reference.split("_")[0]} does not match any of 'Godkend', 'Vent', or 'Slet'")

    orchestrator_connection.log_trace(f"Setting status from {agreement["aktuelStatus"]} to {set_status}")

    payload = {"aftaleid": agreement['id'], "status": set_status, "kommentar": None}
    payload = json.dumps(payload)

    status_resp = requests.post(
        "https://tilslutning.stil.dk/dataadgangadmBE/api/adgang/setStatus",
        headers={
            "Cookie": f"{runtime_args['base_cookie']};{org_cookie}",
            "x-xsrf-token": runtime_args['x-xsrf-token'],
            "accept": "application/json",
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


def process_queue_element(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement):
    """Handles the queue element processing. Changes status, deletes agreement or confirms that status is ok."""
    # State at this point. Manual login done. Lists of organizations retrieved
    # Unpack arguments
    oc_args = json.loads(orchestrator_connection.process_arguments)
    runtime_args = oc_args["runtime_args"]

    # Unpack queue element
    queue_data = json.loads(queue_element.data)
    system_name = queue_data["systemNavn"]
    service_name = queue_data["serviceNavn"]
    current_status = queue_data["status"]
    reference = queue_element.reference
    wanted_status = get_status(reference)

    # Build info dict
    info_dict = {
        "organisation": queue_data["Organisation"],
        "institutionsnr": queue_data["Instregnr"],
        "system navn": system_name,
        "status før (fra kø element)": current_status,
        "ønsket status": wanted_status,
        "reference": queue_element.reference
    }

    # Retrieve organisation
    org_response = get_org(orchestrator_connection, queue_element, runtime_args)
    org_cookie = get_request_cookie("AuthTokenTilslutning", org_response)

    # Retrieve data for organization agreements
    agreements_dict = get_data(orchestrator_connection, queue_element, runtime_args, org_cookie)
    dict_lookup = f"{system_name}_{service_name}_{current_status}"
    agreement = agreements_dict.get(dict_lookup, None)

    # Add info to infodict
    info_dict["aftaleid"] = agreement.get("id", "Id not found")

    if agreement is None:
        dict_lookup_ok = f"{system_name}_{service_name}_{wanted_status}"
        agreement_ok = agreements_dict.get(dict_lookup_ok, None)
        if agreement_ok is not None:
            info_dict["status før (fra fundet aftale)"] = agreement_ok["aktuelStatus"]
            orchestrator_connection.log_trace(f"Status already ok. Info: {info_dict}")
            return
        orchestrator_connection.log_error(f"{system_name = } with {service_name = } and {current_status = } not found in agreements for {info_dict['organisation']} {info_dict['institutionsnr']}")
        raise BusinessError()

    if not agreement['aktuelStatus'] == current_status:
        raise ValueError(
            f"Agreement current status from response: {agreement['aktuelStatus']} " +
            f"does not match current status from queue element: {current_status}"
        )

    orchestrator_connection.log_trace(f"Handling agreement: {system_name = } with {service_name = } and {current_status = } for {info_dict['organisation']} {info_dict['institutionsnr']}")

    if wanted_status in ["GODKENDT", "VENTER"]:
        status_resp = change_status(orchestrator_connection, reference, agreement, runtime_args, org_cookie)

        info_dict["status respons"] = status_resp.text

        orchestrator_connection.log_trace(f"Status successfully changed. Info: {info_dict}")
    elif wanted_status == "SLETTET":
        delete_resp = delete_agreement(orchestrator_connection, agreement, runtime_args, org_cookie)

        info_dict["slet respons"] = delete_resp.text

        orchestrator_connection.log_trace(f"Agreement successfully deleted. Info: {info_dict}")

    return
