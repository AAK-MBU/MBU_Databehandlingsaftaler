"""Main process of the robot"""
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueElement
from robot_framework.subprocesses.queue_handling import process_queue_element


def process(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement):
    """Runs process"""
    process_queue_element(orchestrator_connection, queue_element)
