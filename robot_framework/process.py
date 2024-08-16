"""This module contains the main process of the robot."""

from datetime import datetime
import os
import pandas as pd
import json
import pyodbc

from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses import overview_creation
from robot_framework.subprocesses import queue_upload


def process(orchestrator_connection: OrchestratorConnection) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")

    try:
        connection_string = orchestrator_connection.get_constant('DbConnectionString').value
        oc_args_json = json.loads(orchestrator_connection.process_arguments)
        process_arg = oc_args_json['process']
        base_dir = oc_args_json['base_dir']

        if process_arg == 'create_overview':
            orchestrator_connection.log_trace("Starting overview creation.")
            overview_creation.main(base_dir, connection_string)
            orchestrator_connection.log_trace("Overview creation completed.")
            
        elif process_arg == 'update_status':
            orchestrator_connection.log_trace("Starting update status process. Starting subprocess: retrieve changes.")
            approve_data, delete_data, wait_data = queue_upload.retrieve_changes(base_dir)
            orchestrator_connection.log_trace("Subprocess retrieve changes completed. Starting subprocess: upload to queue.")
            queue_upload.upload_to_queue(approve_data, delete_data, wait_data, orchestrator_connection)
            orchestrator_connection.log_trace("Subprocess upload to queue completed.")

            # Logic for approving, deleting, and waiting aftaler isn't implemented yet.
        else:
            raise ValueError(f"Invalid process: {process}") 
    
    except pyodbc.Error as e:
        orchestrator_connection.log_trace(f"Database error: {str(e)}")
    except ValueError as e:
        orchestrator_connection.log_trace(f"Value error: {str(e)}")
    except Exception as e:
        orchestrator_connection.log_trace(f"Unexpected error: {str(e)}")