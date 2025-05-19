"""This module handles creation of overview"""
import json
import os
import pandas as pd
from tqdm import tqdm
from requests import Session
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses.helper_functions import (
    open_stil_connection,
    get_base_cookies,
    get_browser_cookie,
    get_request_cookie,
    get_org_dict,
    get_org,
    get_data,
    flatten_dict
)
from robot_framework.exceptions import ResponseError


def run_overview_creation(orchestrator_connection: OrchestratorConnection):
    """Runs overview creation"""
    oc_args = json.loads(orchestrator_connection.process_arguments)

    browser = open_stil_connection()
    # Get auth cookies from main page with list of institutioner
    base_cookie, x_xsrf_token = get_base_cookies(browser)
    cookie_inst_list = get_browser_cookie("AuthTokenTilslutning", browser)
    # Get list of organisations, and load payloads for request posts into dict
    session = Session()
    session.headers.update({
        "cookie": base_cookie+";"+cookie_inst_list,
        "x-xsrf-token": x_xsrf_token,
        "accept": "application/json",
        "content-type": "application/json",
        "Accept": "*/*"
    })
    org_dict = get_org_dict(session)

    runtime_args = {
        "base_cookie": base_cookie,
        "x-xsrf-token": x_xsrf_token,
        "cookie_inst_list": cookie_inst_list,
        "org_dict": org_dict,
    }

    all_agreements = []

    # Get agreements from each organization
    orchestrator_connection.log_trace(f"Fetching agreements from {len(org_dict.keys())} institutions")
    for k, v in tqdm(org_dict.items()):
        queue_element = {"Organisation": v["type"], "Instregnr": v["kode"]}
        org_response = get_org(orchestrator_connection, queue_element, runtime_args, session)

        if not org_response.status_code == 200:
            orchestrator_connection.log_error("Error while accessing organization in overview creation")
            raise ResponseError(org_response)

        # Load agreements
        org_cookie = get_request_cookie("AuthTokenTilslutning", org_response)
        session.headers.update({"Cookie": f"{runtime_args['base_cookie']};{org_cookie}"})
        agreements_dict_raw = get_data(orchestrator_connection, queue_element, session)
        # Format agreements and append to all agreements
        agreements = [flatten_dict(vv) for vv in agreements_dict_raw.values()]
        for agreement in agreements:
            agreement["inst_kode"] = agreement.pop("ejer")
            agreement["inst_navn"] = v['navn']
            all_agreements.append(agreement)

    # Store all agreements in directory
    agreements_df = pd.DataFrame(all_agreements)
    base_dir = oc_args["base_dir"]
    filename = os.path.join(base_dir, "alle_dataaftaler.csv")
    agreements_df.to_csv(filename, index=None)

    orchestrator_connection.log_trace(f"{len(all_agreements)} dataaftaler fetched and stored in {base_dir}")
