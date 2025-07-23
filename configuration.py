import json
import sys
import datetime
import pytz
import pandas as pd
import os

from exceptions import UserException


class Configuration:
    def __init__(self, root_directory="/data", code_directory="/code"):
        self.root = root_directory
        self.code_directory = code_directory

        # Načti konfigurační soubor
        config_path = os.path.join(self.root, "config.json")
        # print("Loaded config_data:", json.dumps(config_data, indent=2))
        try:
            with open(config_path, 'r') as file:
                config_data = json.load(file)
        except Exception as e:
            print(f"❌ Chyba při načítání config.json: {e}", file=sys.stderr)
            sys.exit(1)

        self.parameters = config_data.get("parameters", {})
        self.image_params = config_data.get("image_parameters", {})

        # Z parametrů
        self.incremental = bool(self.parameters.get("incremental", False))
        self.tableau_token_name = self.parameters.get("tableau_token_name")
        self.tableau_token_secret = self.parameters.get("#tableau_token_secret")
        self.server = self.parameters.get("server")
        self.site = self.parameters.get("site")
        self.api_version = self.parameters.get("api_version") or self.image_params.get("api_version")
        self.gmail_address = self.parameters.get("gmail_address")
        self.gmail_pass = self.parameters.get("#gmail_pass")
        self.run_specific_email = self.parameters.get("run_specific_email", "")
        self.folder_id = self.parameters.get("folder_id", "")

        # Z image_parameters
        # Z image_parameters
        self.timing_rule = self.image_params.get("timing", {})
        self.gmail_port = self.image_params.get("gmail_port", 587)
        self.imap_port = self.image_params.get("imap_port", 993)
        self.allowed_workbook_format = self.image_params.get("allowed_workbook_format", [])
        self.allowed_view_format = self.image_params.get("allowed_view_format", [])
        self.user_token = self.image_params.get("user_token", {})

        # ➤ Rozdělené service účty:
        self.service_account_post = self.image_params.get("service_account_post", {})
        self.service_account_read = self.image_params.get("service_account_read", {})

        # Schéma výstupních tabulek (volitelně můžeš oddělit)
        self.schemas = {
            "tables": [
                {
                    "name": "table1",
                    "columns": ["id", "col1", "col2"],
                    "primary_keys": ["id"]
                },
                {
                    "name": "table2",
                    "columns": ["id", "col1", "col2", "col3"],
                    "primary_keys": ["id"]
                }
            ]
        }

    def get_input_data(self):
        try:
            self.email_attachments = pd.read_csv(f"{self.root}/in/tables/EMAIL_ATTACHMENTS.csv", dtype=str)
            self.emails = pd.read_csv(f"{self.root}/in/tables/EMAILS.csv", dtype=str)
            self.email_subscribers = pd.read_csv(f"{self.root}/in/tables/EMAIL_SUBSCRIBERS.csv", dtype=str)
        except Exception as e:
            print(f'Chyba při načítání vstupních dat: {e}')
            sys.exit()

    def filter_subscribers(self):
        self.active_subscribers = self.email_subscribers.loc[self.email_subscribers.IS_ACTIVE != 'disabled']

    def filter_emails(self):
        if self.run_specific_email:
            self.email_queue = self.emails.loc[
                (self.emails.MODE != 'deprecated') &
                (self.emails.PERIODICITY == 'run') &
                (self.emails.EMAIL_ID == self.run_specific_email)
            ]
            print(f"Running only specific email: {self.run_specific_email}")
        else:
            run_time = datetime.datetime.now(pytz.timezone("Europe/Prague"))

            the_timing = ""
            for name, hours in self.timing_rule.items():
                if hours[0] < hours[1]:
                    if hours[0] <= run_time.hour < hours[1]:
                        the_timing = name
                elif run_time.hour >= hours[0] or run_time.hour < hours[1]:
                    the_timing = name

            the_weekly_periodicity = run_time.weekday() + 1
            the_monthly_periodicity = run_time.day

            print(f"Running emails – timing: {the_timing}, monthly: {the_monthly_periodicity}, weekly: {the_weekly_periodicity}")

            self.email_queue = self.emails.loc[
                (self.emails.MODE != 'deprecated') &
                (
                    ((self.emails.PERIODICITY == 'weekly') & (self.emails.PERIODICITY_SPECIFICATION == str(the_weekly_periodicity))) |
                    ((self.emails.PERIODICITY == 'monthly') & (self.emails.PERIODICITY_SPECIFICATION == str(the_monthly_periodicity))) |
                    (self.emails.PERIODICITY == 'daily')
                ) &
                (self.emails.TIMING == the_timing)
            ]

    def identify_attachments(self, tbl):
        tmp_attachments = self.email_attachments[self.email_attachments.EMAIL_ID.isin(self.email_queue.EMAIL_ID)]
        self.current_attachments = tmp_attachments.copy()

        for i, row in tmp_attachments.iterrows():
            if pd.isna(row.LUID):
                workbook_LUID = tbl.workbooks.loc[
                    (tbl.workbooks[1] == row.WORKBOOK) & (tbl.workbooks[8] == row.PROJECT)
                ][0].values

                if len(workbook_LUID) != 1:
                    raise Exception(f"Ambiguous Tableau workbook: {row.PROJECT}/{row.WORKBOOK} – {row.EMAIL_ID}")
                workbook_LUID = workbook_LUID[0]

                if row.TABLEAU_OBJECT == "workbook":
                    self.current_attachments.loc[i, "LUID"] = workbook_LUID
                elif row.TABLEAU_OBJECT == "view":
                    views = tbl.get_views_of_workbook(workbook_LUID)
                    view_LUID = views.loc[views[3] == row.VIEW][2].values
                    if len(view_LUID) != 1:
                        raise Exception(f"Ambiguous Tableau view: {row.PROJECT}/{row.WORKBOOK}/{row.VIEW} – {row.EMAIL_ID}")
                    self.current_attachments.loc[i, "LUID"] = view_LUID[0]
            else:
                if row.TABLEAU_OBJECT == "workbook":
                    try:
                        tbl.auth_TSC().workbooks.get_by_id(row.LUID)
                    except KeyError:
                        raise UserException(f"Workbook {row.LUID} not found ({row.EMAIL_ID})")
                elif row.TABLEAU_OBJECT == "view":
                    try:
                        tbl.auth_TSC().views.get_by_id(row.LUID)
                    except KeyError:
                        raise UserException(f"View {row.LUID} not found ({row.EMAIL_ID})")
