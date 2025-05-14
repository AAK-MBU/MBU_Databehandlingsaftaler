"""This module handles creation of overview"""
from tqdm import tqdm
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses.helper_functions import (
    open_stil_connection,
    get_base_cookies,
    get_browser_cookie,
    get_request_cookie,
    get_inst_dict,
    get_dag_dict,
    get_org,
    get_data,
)
from robot_framework.exceptions import ResponseError


def run_overview_creation(orchestrator_connection: OrchestratorConnection):
    """Runs overview creation"""
    browser = open_stil_connection()
    # Get auth cookies from main page with list of institutioner
    base_cookie, x_xsrf_token = get_base_cookies(browser)
    cookie_inst_list = get_browser_cookie("AuthTokenTilslutning", browser)
    # Get list of organisations, and load payloads for request posts into dict
    inst_payload_dict = get_inst_dict(base_cookie, cookie_inst_list)
    dag_payload_dict = get_dag_dict(base_cookie, cookie_inst_list)

    org_dict = inst_payload_dict | dag_payload_dict

    runtime_args = {
        "base_cookie": base_cookie,
        "x-xsrf-token": x_xsrf_token,
        "cookie_inst_list": cookie_inst_list,
        "org_dict": org_dict,
    }

    all_agreements = {}

    for k, v in tqdm(org_dict.items()):
        queue_element = {"Organisation": v["type"], "Instregnr": v["kode"]}
        org_response = get_org(orchestrator_connection, queue_element, runtime_args)

        if not org_response.status_code == 200:
            orchestrator_connection.log_error("Error while accessing organization in overview creation")
            raise ResponseError(org_response)
        
        org_cookie = get_request_cookie("AuthTokenTilslutning", org_response)
        agreements_dict_raw = get_data(orchestrator_connection, queue_element, runtime_args, org_cookie)
        agreements = [v for v in agreements_dict_raw.values()]
        all_agreements[k] = agreements

    print("should have fetched all agreements")
