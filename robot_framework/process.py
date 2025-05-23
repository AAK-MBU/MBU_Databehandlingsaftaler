"""This module contains the main process of the robot."""
import os
import json
import pyodbc
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueStatus
from robot_framework.subprocesses.overview_creation import run_overview_creation
from robot_framework.subprocesses.queue_upload import retrieve_changes, upload_to_queue
from robot_framework.subprocesses.queue_handling import process_queue_elements


def process(orchestrator_connection: OrchestratorConnection) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running main process.")

    try:
        # connection_string = orchestrator_connection.get_constant('DbConnectionString').value
        connection_string = os.getenv('DbConnectionString')  # For testing
        oc_args_json = json.loads(orchestrator_connection.process_arguments)
        process_arg = oc_args_json['process']

        if process_arg == 'create_overview':
            base_dir = oc_args_json['base_dir']
            notification_mail = oc_args_json['notification_mail']
            dagtilbud = oc_args_json['dagtilbud']
            institutioner = oc_args_json['institutioner']
            orchestrator_connection.log_trace("Starting overview creation.")
            run_overview_creation(base_dir, connection_string, notification_mail, dagtilbud, institutioner)
            orchestrator_connection.log_trace("Overview creation completed.")

        elif process_arg == 'upload_and_handle_queue':
            # Delete all elements in the queue before uploading new ones
            base_dir = oc_args_json['base_dir']

            # Retrieve changes and upload
            orchestrator_connection.log_trace("Retrieving changes from overview.")
            approve_data, delete_data, wait_data = retrieve_changes(base_dir)
            orchestrator_connection.log_trace("Changes retrieved. Uploading to queue.")
            upload_to_queue(approve_data, delete_data, wait_data, orchestrator_connection)
            orchestrator_connection.log_trace("Queue upload completed.")

            # Handle queue elements
            queue_elements = orchestrator_connection.get_queue_elements("Databehandlingsaftale_Status_Queue")
            if queue_elements:
                orchestrator_connection.log_trace(f"Handling {len(queue_elements)} queue elements.")
                process_queue_elements(queue_elements, orchestrator_connection)
                orchestrator_connection.log_trace("Queue handling completed.")

        elif process_arg == 'queue_upload':
            # Delete all elements in the queue before uploading new ones
            base_dir = oc_args_json['base_dir']

            orchestrator_connection.log_trace("Retrieving changes from overview.")
            approve_data, delete_data, wait_data = retrieve_changes(base_dir)
            orchestrator_connection.log_trace(f"{len(approve_data)+len(delete_data)+len(wait_data)} changes retrieved. Uploading to queue.")
            upload_to_queue(approve_data, delete_data, wait_data, orchestrator_connection)
            orchestrator_connection.log_trace("Queue upload completed.")

        elif process_arg == 'handle_queue':
            queue_elements = orchestrator_connection.get_queue_elements(queue_name="Databehandlingsaftale_Status_Queue", status=QueueStatus.NEW, limit=1000)
            if queue_elements:
                orchestrator_connection.log_trace(f"Handling {len(queue_elements)} queue elements.")
                process_queue_elements(queue_elements, orchestrator_connection)
                orchestrator_connection.log_trace("Queue handling completed.")

        else:
            raise ValueError(f"Invalid process: {process_arg}")

    except pyodbc.Error as error:
        orchestrator_connection.log_trace(f"Database error: {str(error)}")

    except ValueError as e:
        orchestrator_connection.log_trace(f"Value error: {str(e)}")
