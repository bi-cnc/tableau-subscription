import json
import sys
import datetime
import pytz
import pandas as pd
import os

from exceptions import UserException


def _safe_keys(d):
    try:
        return list(d.keys())
    except Exception:
        return []

class Configuration:
    def __init__(self, root_directory="/data", code_directory="/code"):
        self.root = root_directory
        self.code_directory = code_directory

        # Načti config.json
        config_path = os.path.join(self.root, "config.json")
        try:
            with open(config_path, 'r') as file:
                config_data = json.load(file)
        except Exception as e:
            print(f"❌ Chyba při načítání config.json: {e}", file=sys.stderr)
            sys.exit(1)

        # Parametry z config.json (UI)
        self.parameters = config_data.get("parameters", {})
        self.image_params = config_data.get("image_parameters", {})  # fallback

        # === STACK PARAMETERS loader (robustní) ===
        stack_params_env = os.environ.get("KBC_STACK_PARAMETERS")
        stack_params = {}
        if stack_params_env:
            print("ℹ️ KBC_STACK_PARAMETERS present: True")
            print("ℹ️ KBC_STACK_PARAMETERS head:", stack_params_env[:200].replace("\n", " "))
            try:
                parsed = json.loads(stack_params_env)
                if "connection.eu-central-1.keboola.com" in parsed:
                    stack_params = parsed["connection.eu-central-1.keboola.com"]
                    print("ℹ️ Using region key: connection.eu-central-1.keboola.com")
                else:
                    stack_params = parsed
                    print("ℹ️ Using stack params without region key (flattened).")
            except Exception as e:
                print(f"⚠️ Nelze parse-ovat KBC_STACK_PARAMETERS: {e}", file=sys.stderr)
        else:
            print("ℹ️ KBC_STACK_PARAMETERS present: False")

        # primární zdroj stack-like parametrů
        sp = stack_params or self.image_params or {}
        src = "KBC_STACK_PARAMETERS" if stack_params else ("image_parameters (fallback)" if self.image_params else "EMPTY")
        print(f"ℹ️ Stack-like param source: {src}; keys: {_safe_keys(sp)}")
        print(f"ℹ️ image_parameters keys: {_safe_keys(self.image_params)}")

        # Z parameters (UI)
        self.incremental = bool(self.parameters.get("incremental", False))
        self.tableau_token_name = self.parameters.get("tableau_token_name")
        self.tableau_token_secret = self.parameters.get("#tableau_token_secret")
        self.server = self.parameters.get("server")
        self.site = self.parameters.get("site")
        self.gmail_address = self.parameters.get("gmail_address")
        self.gmail_pass = self.parameters.get("#gmail_pass")
        self.run_specific_email = self.parameters.get("run_specific_email", "")
        self.folder_id = self.parameters.get("folder_id", "")

        # Z stack/image parameters
        self.timing_rule = sp.get("timing", {})
        self.gmail_port = sp.get("gmail_port", 465)
        self.imap_port = sp.get("imap_port", 993)
        self.allowed_workbook_format = sp.get("allowed_workbook_format", [])
        self.allowed_view_format = sp.get("allowed_view_format", [])
        self.user_token = sp.get("user_token", {})
        self.service_account_post = sp.get("service_account_post", {})
        self.service_account_read = sp.get("service_account_read", {})
        self.api_version = self.parameters.get("api_version") or sp.get("api_version", 3.9)

        # Debug – rychlá kontrola klíčů (bez citlivých hodnot)
        print("🔎 service_account_post keys:", _safe_keys(self.service_account_post))
        print("🔎 service_account_read  keys:", _safe_keys(self.service_account_read))
        print("🔎 timing_rule present:", bool(self.timing_rule))
        print("🔎 ports:", {"gmail_port": self.gmail_port, "imap_port": self.imap_port})
        print("🔎 allowed formats:", {
            "workbook": self.allowed_workbook_format,
            "view": self.allowed_view_format
        })

        # Schéma výstupních tabulek (volitelné)
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
