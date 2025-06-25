"""This module handles creation of overview"""
import json
import time
import os
from datetime import datetime
import pandas as pd
from tqdm import tqdm
from requests import Session
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from openpyxl.worksheet.datavalidation import DataValidation

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


def store_overview(agreements_df: pd.DataFrame, base_dir: str):
    """Function to store overview as excel"""
    agreements_df["statusændring"] = ""
    cols_left = ["Instregnr", "inst_navn", "status", "statusændring", "systemNavn", "systemBeskrivelse", "serviceNavn", "udbyderNavn", "Kontaktperson"]
    agreements_df = agreements_df[cols_left]
    filename = os.path.join(base_dir, "Output", f"dataaftaler_oversigt_{datetime.now().strftime('%d%m%Y')}.xlsx")

    os.makedirs(os.path.join(base_dir, "Output"), exist_ok=True)

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        agreements_df.to_excel(writer, index=False, sheet_name='Oversigt')
        worksheet = writer.sheets['Oversigt']
        worksheet.auto_filter.ref = worksheet.dimensions

        for row in range(2, worksheet.max_row + 1):
            status_cell = worksheet[f'C{row}']
            statusændring_cell = worksheet[f'D{row}']  # 'statusændring' is in column D
            if status_cell.value != "SLETTET":
                dv = DataValidation(type="list", formula1='"GODKEND, SLET, VENT"')
                dv.error_title = 'Invalid input'
                dv.error_message = 'Please select a value from the dropdown list'
                worksheet.add_data_validation(dv)
                dv.add(statusændring_cell)

        # Adjust column widths but limit the max width
        max_column_width = 30
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    max_length = max(max_length, len(str(cell.value)))
                except (TypeError, ValueError):
                    pass
            adjusted_width = min(max_length + 2, max_column_width)
            worksheet.column_dimensions[column].width = adjusted_width


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
    print(f"Fetching agreements from {len(org_dict.keys())} institutions")
    orgs_without_agr = []
    api_counter = 0
    start = time.time()
    for v in (pbar := tqdm(org_dict.values())):
        if (api_counter >= 200 and time.time() - start < 60):
            wait_msg = f"{api_counter} calls in {time.time()-start:.1f} seconds. Pausing for 30 seconds"
            orchestrator_connection.log_info(wait_msg)
            pbar.write(wait_msg)
            time.sleep(30)
            api_counter = 0
            start = time.time()
            pbar.write("Continuing...")
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
        if len(agreements) == 0:
            orgs_without_agr.append(queue_element)
        for agreement in agreements:
            agreement["Instregnr"] = agreement.pop("ejer")
            agreement["inst_navn"] = v['navn']
            all_agreements.append(agreement)

        api_counter += 2

    # Store all agreements in directory
    agreements_df = pd.DataFrame(all_agreements)
    # Rename columns
    cols_rename = {
        "inst_kode": "Instregnr",
        "aktuelStatus": "status",
        "stilService_servicenavn": "serviceNavn",
        "udbyderSystemOgUdbyder_navn": "systemNavn",
        "udbyderSystemOgUdbyder_beskrivelse": "systemBeskrivelse",
        "udbyderSystemOgUdbyder_udbyder_navn": "udbyderNavn",
        "udbyderSystemOgUdbyder_kontaktperson_navn": "Kontaktperson"
    }
    agreements_df = agreements_df.rename(columns=cols_rename)
    base_dir = oc_args["base_dir"]
    print(f"{len(all_agreements)} agreements for {len(pd.unique(agreements_df['Instregnr']))} institutions fetched. Storing in {base_dir}")
    orchestrator_connection.log_trace(f"{len(all_agreements)} agreements for {len(pd.unique(agreements_df['Instregnr']))} institutions fetched. Storing in {base_dir}")
    orgs_without_agr_print = '\n'.join([str(i) for i in orgs_without_agr])
    print(f"{len(orgs_without_agr)} institutions have no dataagreements: {orgs_without_agr_print}")
    orchestrator_connection.log_trace(f"{len(orgs_without_agr)} institutions have no dataagreements: {orgs_without_agr_print}")
    store_overview(agreements_df, base_dir)

    orchestrator_connection.log_trace(f"{len(all_agreements)} dataaftaler fetched and stored in {base_dir}")
