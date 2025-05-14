"""This module defines any initial processes to run when the robot starts."""

import json
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from robot_framework.subprocesses.queue_upload import upload_to_queue, retrieve_changes
from robot_framework.subprocesses.overview_creation import run_overview_creation


def initialize(orchestrator_connection: OrchestratorConnection) -> None:
    """Do all custom startup initializations of the robot."""
    orchestrator_connection.log_trace("Initializing.")
    oc_args = json.loads(orchestrator_connection.process_arguments)
    if "upload" in oc_args["process"]:
        base_dir = oc_args['base_dir']

        # Retrieve changes and upload
        orchestrator_connection.log_trace("Retrieving changes from overview.")
        approve_data, delete_data, wait_data = retrieve_changes(base_dir)
        orchestrator_connection.log_trace("Changes retrieved. Uploading to queue.")
        upload_to_queue(approve_data, delete_data, wait_data, orchestrator_connection)
        orchestrator_connection.log_trace("Queue upload completed.")
    if "overview" in oc_args["process"]:
        connection_string = orchestrator_connection.get_constant("DbConnectionString").value
        base_dir = oc_args['base_dir']
        notification_mail = oc_args['notification_mail']
        # dagtilbud = oc_args['dagtilbud']
        # institutioner = oc_args['institutioner']
        orchestrator_connection.log_trace("Starting overview creation.")
        run_overview_creation(orchestrator_connection)
        orchestrator_connection.log_trace("Overview creation completed.")