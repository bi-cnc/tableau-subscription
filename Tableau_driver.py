

##### Tableau_driver.py

import xml.etree.ElementTree as ET # Contains methods used to build and parse XML
import requests as r
import tableauserverclient as TSC
import pandas as pd


class Tableau:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base_url = "{0}/api/{1}/".format(cfg.server,'3.23') # todo upravit hardcoded url
        self.get_workbooks()

    def _encode_for_display(self,text):
        """
        Encodes strings so they can display as ASCII in a Windows terminal window.
        This function also encodes strings for processing by xml.etree.ElementTree functions.

        Returns an ASCII-encoded version of the text.
        Unicode characters are converted to ASCII placeholders (for example, "?").
        """
        return text.encode('ascii', errors="backslashreplace").decode('utf-8')

    def login(self):

        xmlns = {'t': 'http://tableau.com/api'}
        # Builds the request
        xml_request = ET.Element('tsRequest')
        credentials_element = ET.SubElement(xml_request,
                                            'credentials',
                                            personalAccessTokenName=self.cfg.tableau_token_name,
                                            personalAccessTokenSecret=self.cfg.tableau_token_secret)

        ET.SubElement(credentials_element, 'site', contentUrl=self.cfg.site)
        xml_request = ET.tostring(xml_request)
        s = r.session()
        server_response = s.post(self.base_url + 'auth/signin', data=xml_request)

        if server_response.status_code == 200:
            print("Tableau server succesfully authorized.")
        else:
            raise Exception("Unable to login with server response:" + str(server_response.status_code) + server_response.text)

        # ASCII encode server response to enable displaying to console
        server_response = self._encode_for_display(server_response.text)
        # Reads and parses the response
        parsed_response = ET.fromstring(server_response)
        # Gets the auth token and site ID
        token = parsed_response.find('t:credentials', namespaces=xmlns).get('token')
        self.site_id = parsed_response.find('.//t:site', namespaces=xmlns).get('id')
        s.headers = {'x-tableau-auth': token}
        return s

    def auth_TSC(self):
        tableau_auth = TSC.PersonalAccessTokenAuth(self.cfg.tableau_token_name, self.cfg.tableau_token_secret, self.cfg.site)
        # tableau_auth = TSC.TableauAuth(self.cfg.login, self.cfg.password, self.cfg.site)
        server = TSC.Server(self.cfg.server)
        server.auth.sign_in(tableau_auth)
        server.use_server_version()
        request_options = TSC.RequestOptions(pagesize=10000)
        return server

    def get_workbooks(self):
        tmp_server= self.auth_TSC()
        all_workbooks = list(TSC.Pager(tmp_server.workbooks))
        workbooks = []
        for workbook in all_workbooks:
            workbooks.append([workbook.id, workbook.name, workbook.content_url, workbook.webpage_url,
                          workbook.owner_id, workbook.created_at, workbook.updated_at,
                          workbook.project_id, workbook.project_name, str([tag for tag in workbook.tags]),
                          workbook.show_tabs, workbook.size, workbook.description])
        self.workbooks = pd.DataFrame(workbooks)


    def get_views_of_workbook(self,workbook_LUID):
        tmp_server = self.auth_TSC()
        ### return pd.DataFrame with all views datails for specified workbook_LUID
        workbook_views = []
        #getting workbook object
        the_workbook = tmp_server.workbooks.get_by_id(workbook_LUID)
        #populating views
        tmp_server.workbooks.populate_views(the_workbook, usage=True)
        #reshaping to the dataframe
        for view in the_workbook.views:
            workbook_views.append([the_workbook.id, the_workbook.name, view.id, view.name, view.content_url,
                                   view.sheet_type, view.total_views])
        return pd.DataFrame(workbook_views)

