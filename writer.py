

##### writer.py

import os
import re


class Writer:
    def __init__(self, configuration, table_name):
        self.table_name = table_name
        self.cfg = configuration
        self.part_number = 0
        # get metadata for the table
        self.header = configuration.schemas["tables"][
            next((index for (index, d) in enumerate(configuration.schemas["tables"]) if d["name"] == table_name),
                 None)]
        # create csv folder if non-existent
        if not os.path.exists(f"{self.cfg.root}out/tables/{self.table_name}.csv/"):
            os.makedirs(f"{self.cfg.root}out/tables/{self.table_name}.csv/")
        # create a manifest file if non-existent
        if not os.path.exists(f"{self.cfg.root}out/tables/{self.table_name}.csv.manifest"):
            self.cfg.cfg.write_table_manifest(f"{self.cfg.root}out/tables/{self.table_name}.csv",
                                              columns=self.header["columns"],
                                              primary_key=self.header["primary_keys"],
                                              incremental = self.cfg.incremental)

    def __rename_and_reduce_columns(self, data_frame):
        #pattern = re.compile(r'\.')
        #data_frame = data_frame.rename(index=str, columns=lambda x: re.sub(pattern, '_', x))
        for k in self.header["columns"]:
            if k not in data_frame.columns.tolist():
                data_frame[k] = ""
        data_frame = data_frame[self.header["columns"]]
        return data_frame

    def export_to_csv(self, table_data):
        # remove stray columns
        #if table_data is not None:
        #    table_data = self.__rename_and_reduce_columns(table_data)
        # write one partial csv to the csv folder
        if table_data is not None and not table_data.empty:
            table_data.to_csv(f"{self.cfg.root}out/tables/{self.table_name}.csv/part{self.part_number}",
                              header=False,
                              index=False)
            self.part_number += 1

