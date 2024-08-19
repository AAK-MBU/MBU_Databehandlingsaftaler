"""This module contains the main process of the robot."""

from datetime import datetime
import os
import json
import pyodbc

from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses.overview_creation import run
from robot_framework.subprocesses.queue_upload import retrieve_changes, upload_to_queue

def process(orchestrator_connection: OrchestratorConnection) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running main process.")

    try:
        connection_string = orchestrator_connection.get_constant('DbConnectionString').value
        oc_args_json = json.loads(orchestrator_connection.process_arguments)
        process_arg = oc_args_json['process']
        base_dir = oc_args_json['base_dir']

        if process_arg == 'create_overview':
            orchestrator_connection.log_trace("Starting overview creation.")
            run(base_dir, connection_string)
            orchestrator_connection.log_trace("Overview creation completed.")

        if process_arg == 'queue_upload':
            orchestrator_connection.log_trace("Retrieving changes from overview.")
            approve_data, delete_data, wait_data = retrieve_changes(base_dir)
            orchestrator_connection.log_trace("Changes retrieved. Uploading to queue.")
            upload_to_queue(approve_data, delete_data, wait_data, orchestrator_connection)
            orchestrator_connection.log_trace("Queue upload completed.")

        if process_arg == 'delete_element':
            orchestrator_connection.delete_queue_element("ba0356aa-2505-4cdc-b285-3861af7e5045")

        else:
            raise ValueError(f"Invalid process: {process_arg}")
    
    except pyodbc.Error as e:
        orchestrator_connection.log_trace(f"Database error: {str(e)}")
    except ValueError as e:
        orchestrator_connection.log_trace(f"Value error: {str(e)}")
    except Exception as e:
        orchestrator_connection.log_trace(f"Unexpected error: {str(e)}")



if __name__ == "__main__":
    json_args = '{"process": "delete_element", "base_dir": "C:\\\\Users\\\\az77879\\\\OneDrive - Aarhus kommune\\\\MergeCvs_dataaftaler_testdata"}'
    oc = OrchestratorConnection("Dataaftaler - queue upload test", os.getenv('OpenOrchestratorConnStringTest'), os.getenv('OpenOrchestratorKeyTest'), json_args)
    process(oc)
