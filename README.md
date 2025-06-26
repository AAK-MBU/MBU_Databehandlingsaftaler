# Dataaftaler

Hurtigt overblik over eksisterende dataaftaler, samt opdatering af aftaler i STIL.

Robotten har tre dele:
1. **[Overview creation](#overview-creation)** <br>
    Eksporterer et Excel-ark med alle eksisterende dataaftaler
2. **[Upload queue](#upload-queue)** <br>
    Uploader dataaftaler, som skal opdateres, til OpenOrchestrator kø
3. **[Handle queue](#handle-queue)** <br>
    Opdaterer dataaftaler i STIL.

For at køre robotten kræver det følgende:
- Adgang til [tilslutning.stil.dk](https://tilslutning.stil.dk)
- [OpenOrchestrator](https://pypi.org/project/OpenOrchestrator/) opsætning

Robotten fungerer som en "attended" robot, og agerer på vegne af en medarbejder, som logger ind.
Robottens nuværende konfiguration, antager at medarbejderen er ansat i Aarhus Kommune, og tilgår Lokal IdP for Aarhus Kommune.

## Overview creation

Robotten eksporterer et Excelark med alle eksisterende dataaftaler fundet i STIL. Arket eksporteres til `base_dir`/Output.
Dette foregår i tre trin:
1. Robotten tilgår login-siden til [STIL](https://tilslutning.stil.dk). Her skal brugeren af robotten selv logge ind.
2. Robotten tilgår alle de listede institutioner, og henter deres dataaftaler
3. Roboten eksporterer aftalerne til et Excel-ark.

I Excel-arket bliver kolonnen "statusændring" tilføjet, med mulighed for at vælge hvilken status aftalen skal ændres til: "VENTER" "GODKEND" eller "SLET".

Robotten pauser i 30 sekunder for hvert 200. API-kald (svarende til hver 100. institution).

## Upload queue

Robotten modtager ændringer i dataftaler fra [Excel-arket](#overview-creation).
Ændringerne er specificeret af kolonnen 'statusændring', og disse ændringer indlæses så i OpenOrchestrator kø.
For at robotten kan finde Excel-arket med de specificerede ændringer, skal arket gemmes som det eneste Excel-ark i `base_dir`/Output.

## Handle queue

Robotten opdaterer de dataaftaler som er specificeret i den kø, der er blevet oprettet i [Upload changes to queue](#upload-changes-to-queue).
Dette foregår i 2 trin:
1. Robotten tilgår login-siden til [STIL](https://tilslutning.stil.dk). Her skal brugeren af robotten selv logge ind.
2. Robotten opdaterer de dataaftaler, som skal er defineret i [køen](#upload-changes-to-queue)

## Brug af robotten

Robotten køres gennem [OpenOrchestrator](https://pypi.org/project/OpenOrchestrator/) ([dokumentation](https://itk-dev-rpa.github.io/OpenOrchestrator-docs/)). Her angives følgende i proces_arguments:
- "process": "create_overview", "upload_queue" eller "handle_queue"
- "base_dir": [sti til der, hvor filer skal gemmes] 
