"""This module handles retrieving changes in dataaftaler and uploading them to queue."""
import pandas as pd
import os
import glob
from datetime import datetime
import json
import hashlib

from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection


def retrieve_changes(base_dir):
    """
    Retrieves and filters data from the Dataaftaler overview created with the create_overview process.

    Args:
        base_dir (str): The base directory for all Dataaftaler-processes.
    
    Returns:
        tuple: A tuple containing three lists of dictionaries:
            - approve_data (list of dict): Aftaler to be marked as GODKENDT in STIL.
            - delete_data (list of dict): Aftaler to be marked as SLETTET in STIL.
            - wait_data (list of dict): Aftaler to marked as VENTER in STIL.
    
    Raises:
        ValueError: If there is more than one Oversigt excel files in the 'Output' directory.
    
    Notes:
        - The function expects an 'Output' folder inside the given base directory containing exactly one Excel file.
        - The Excel file must have columns 'statusændring', 'status', 'Organisation', 'Instregnr', 'systemNavn', and 'serviceNavn'.
    """
    file_path = os.path.join(base_dir, "Output")
    excel_files = glob.glob(os.path.join(file_path, '*Oversigt*.xlsx'))
    if len(excel_files) == 1:
        df = pd.read_excel(excel_files[0])
    else:
        raise ValueError("There should be exactly one Oversigt file in the directory. Delete old files.")

    filtered_approve_df = df[(df['statusændring'] == 'GODKEND') & (df['status'] != 'GODKENDT')]
    filtered_delete_df = df[(df['statusændring'] == 'SLET') & (df['status'] != 'SLETTET')]
    filtered_wait_df = df[(df['statusændring'] == 'VENT') & (df['status'] != 'VENTER')]

    approve_data = filtered_approve_df[['Organisation', 'Instregnr', 'systemNavn', 'serviceNavn', 'status']].dropna().to_dict(orient='records')
    delete_data = filtered_delete_df[['Organisation', 'Instregnr', 'systemNavn', 'serviceNavn', 'status']].dropna().to_dict(orient='records')
    wait_data = filtered_wait_df[['Organisation', 'Instregnr', 'systemNavn', 'serviceNavn', 'status']].dropna().to_dict(orient='records')

    return approve_data, delete_data, wait_data


def generate_short_hash(data, length=8):
    """
    Generate a short hash based on input data.

    Args:
        data (str): The data to generate the hash from.
        length (int): The length of the desired hash.

    Returns:
        str: The short hash.
    """
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)
    hash_object = hashlib.md5(data.encode())
    return hash_object.hexdigest()[:length] 

def upload_to_queue(approve_data, delete_data, wait_data, orchestrator_connection):
    """
    Uploads the processed data to a queue in the Orchestrator.

    Args:
        approve_data (list of dict): List of dictionaries containing Aftaler to be approved.
        delete_data (list of dict): List of dictionaries containing Aftaler to be deleted.
        wait_data (list of dict): List of dictionaries containing Aftaler to be waiting.
        orchestrator_connection (OrchestratorConnection): An instance of the OrchestratorConnection used to interact with the Orchestrator.

    Returns:
        None
    """
    approve_data_json = [json.dumps(data) for data in approve_data]
    delete_data_json = [json.dumps(data) for data in delete_data]
    wait_data_json = [json.dumps(data) for data in wait_data]

    approve_references = [f"Godkend_{generate_short_hash(data)}" for data in approve_data]
    delete_references = [f"Slet_{generate_short_hash(data)}" for data in delete_data]
    wait_references = [f"Vent_{generate_short_hash(data)}" for data in wait_data]

    orchestrator_connection.bulk_create_queue_elements("Databehandlingsaftale_Status_Queue", references=approve_references, data=approve_data_json)
    orchestrator_connection.bulk_create_queue_elements("Databehandlingsaftale_Status_Queue", references=delete_references, data=delete_data_json)
    orchestrator_connection.bulk_create_queue_elements("Databehandlingsaftale_Status_Queue", references=wait_references, data=wait_data_json)