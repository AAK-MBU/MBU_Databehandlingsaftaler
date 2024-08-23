# Databehandlingsaftaler

A robot designed to streamline two processes when working with databehandlingsaftaler in STIL.

## Overview Creation

This process exports agreements for all institutioner and dagtilbud and creates an overview.
A column titled "statusændring" is added to mark a new status with "VENTER," "GODKEND," or "SLET."

### Usage

You can run the process either locally or from OpenOrchestrator by triggering `Dataaftaler_Create_Overview`.
Make sure to include the following process arguments: 
- `"process": "create_overview"`
- `"base_dir": <directory_path>`
- `"notification_email": <email_address>`

## Updating Changes

To initiate the robot and apply changes from the overview, ensure that the overview file is placed in a folder named "Output" within the `base_dir`.
The robot retrieves the changes from the overview and uploads them to a queue in OpenOrchestrator.
Another process then opens STIL and updates the agreements accordingly.