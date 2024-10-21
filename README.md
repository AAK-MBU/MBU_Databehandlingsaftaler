# Databehandlingsaftaler

A robot designed to streamline two processes when working with databehandlingsaftaler in STIL.

## Overview Creation

This robot exports agreements for all institutioner and dagtilbud and creates an overview.
A column titled "statusændring" is added to mark a new status with "VENTER," "GODKEND," or "SLET."

### Usage

You can run the process either locally or from OpenOrchestrator.
Make sure to include the following process arguments: 
- `"process": "create_overview"`
- `"base_dir": <directory_path>`
- `"notification_email": <email_address>`
- `"institutioner": <'False' or 'True' (if you want to include institutioner in the overview creation)>`
- `"Dagtilbud": <'False' or 'True' (if you want to include dagtilbud in the overview creation)>`

## Upload Changes To Queue

This process retrieves the agreements from the overview Excel file where the column 'statusændring' contains "VENTER", "GODKEND", or "SLET". 
Uploads the retrived agreements as element to a queue.
Make sure that the overview file is placed in a folder named "Output" within the `base_dir`.

### Usage

You can run the process either locally or from OpenOrchestrator.
Make sure to include the following process arguments: 
- `"process": "queue_upload"`
- `"base_dir": <directory_path>`


## Updating Changes

This robot opens STIL and changes the status according to the queue elements. 

You can run the process either locally or from OpenOrchestrator.
Make sure to include the following process arguments: 
- `"process": "handle_queue"`
- `"notification_email": <email_address>`
