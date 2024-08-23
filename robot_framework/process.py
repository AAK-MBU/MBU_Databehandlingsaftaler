"""This module contains the main process of the robot."""
import os
import json
import pyodbc
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses.overview_creation import run_overview_creation
from robot_framework.subprocesses.queue_upload import retrieve_changes, upload_to_queue
from robot_framework.subprocesses.queue_handling import run_queue_handling


def process(orchestrator_connection: OrchestratorConnection) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running main process.")

    try:
        # connection_string = orchestrator_connection.get_constant('DbConnectionString').value
        connection_string = os.getenv('DbConnectionString') # For testing
        oc_args_json = json.loads(orchestrator_connection.process_arguments)
        process_arg = oc_args_json['process']

        if process_arg == 'create_overview':
            base_dir = oc_args_json['base_dir']
            notification_mail = oc_args_json['notification_mail']
            orchestrator_connection.log_trace("Starting overview creation.")
            run_overview_creation(base_dir, connection_string, notification_mail)
            orchestrator_connection.log_trace("Overview creation completed.")

        if process_arg == 'queue_upload':
            base_dir = oc_args_json['base_dir']
            orchestrator_connection.log_trace("Retrieving changes from overview.")
            approve_data, delete_data, wait_data = retrieve_changes(base_dir)
            orchestrator_connection.log_trace("Changes retrieved. Uploading to queue.")
            upload_to_queue(approve_data, delete_data, wait_data, orchestrator_connection)
            orchestrator_connection.log_trace("Queue upload completed.")

        if process_arg == 'delete_queue':
            queue_elements = orchestrator_connection.get_queue_elements("Databehandlingsaftale_Status_Queue")
            for element in queue_elements:
                orchestrator_connection.delete_queue_element(element.id)
            orchestrator_connection.log_trace("Databehandlingsaftale_Status_Queue deleted.")

        if process_arg == 'handle_queue':
            queue_elements = orchestrator_connection.get_queue_elements("Databehandlingsaftale_Status_Queue")
            if queue_elements:
                orchestrator_connection.log_trace(f"Handling {len(queue_elements)} queue elements.")
                run_queue_handling(queue_elements, orchestrator_connection)
                orchestrator_connection.log_trace("Queue handling completed.")

        else:
            raise ValueError(f"Invalid process: {process_arg}")

    except pyodbc.Error as e:
        orchestrator_connection.log_trace(f"Database error: {str(e)}")
    except ValueError as e:
        orchestrator_connection.log_trace(f"Value error: {str(e)}")
