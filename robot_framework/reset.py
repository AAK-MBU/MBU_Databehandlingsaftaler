"""This module handles resetting the state of the computer so the robot can work with a clean slate."""

import json
from requests import Session
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses.helper_functions import (
    get_base_cookies,
    get_browser_cookie,
    open_stil_connection,
    get_org_dict,
)


def reset(orchestrator_connection: OrchestratorConnection) -> None:
    """Clean up, close/kill all programs and start them again."""
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
    orchestrator_connection.process_arguments = json.dumps(oc_args)


def close_all(orchestrator_connection: OrchestratorConnection) -> None:
    """Gracefully close all applications used by the robot."""
    orchestrator_connection.log_trace("Closing all applications.")
    if hasattr(orchestrator_connection, "browser"):
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
    session = Session()
    session.headers.update({"cookie": base_cookie + ";" + cookie_inst_list})
    # Get list of organisations, and load payloads for request posts into dict
    org_dict = get_org_dict(session)
    # store in process arguments
    runtime_args = {
        "base_cookie": base_cookie,
        "x-xsrf-token": x_xsrf_token,
        "cookie_inst_list": cookie_inst_list,
        "org_dict": org_dict,
    }
    oc_args = json.loads(orchestrator_connection.process_arguments)
    oc_args["runtime_args"] = runtime_args
    orchestrator_connection.process_arguments = json.dumps(oc_args)
