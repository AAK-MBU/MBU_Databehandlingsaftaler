"""This module contains the queue handling process of the robot."""
import json
from requests import Session
from OpenOrchestrator.database.queues import QueueElement
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.exceptions import BusinessError
from robot_framework.subprocesses.helper_functions import (
    get_org,
    get_data,
    get_request_cookie,
    get_status,
    change_status,
    delete_agreement
)


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
    session = Session()
    session.headers.update({
        "Cookie": f"{runtime_args['base_cookie']};{runtime_args['cookie_inst_list']}",
        "x-xsrf-token": runtime_args['x-xsrf-token'],
    })

    # Retrieve organisation
    org_response = get_org(orchestrator_connection, queue_element, runtime_args, session)
    org_cookie = get_request_cookie("AuthTokenTilslutning", org_response)
    session.headers.update({"Cookie": f"{runtime_args['base_cookie']};{org_cookie}"})

    # Retrieve data for organization agreements
    agreements_dict = get_data(orchestrator_connection, queue_element, session)
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
        status_resp = change_status(orchestrator_connection, reference, agreement, session)

        info_dict["status respons"] = status_resp.text

        orchestrator_connection.log_trace(f"Status successfully changed. Info: {info_dict}")
    elif wanted_status == "SLETTET":
        delete_resp = delete_agreement(orchestrator_connection, agreement, runtime_args, org_cookie)

        info_dict["slet respons"] = delete_resp.text

        orchestrator_connection.log_trace(f"Agreement successfully deleted. Info: {info_dict}")

    return
