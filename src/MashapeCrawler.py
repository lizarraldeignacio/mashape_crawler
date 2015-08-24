#
# mashape.com Crawler
import urllib3
import json
import re
import sqlite3
from bs4 import BeautifulSoup

SERVICE_AVAILABLE_PAGES = 72
#
# Number of available service list pages + 1 (This should be changed for something dynamic)


class MashapeCrawler(object):
    #
    # HTML Parser for extracting mashape.com service list

    def __init__(self, data_base_path):
        self._data_base_connection = sqlite3.connect(data_base_path)
        self._data_base_cursor = self._data_base_connection.cursor()
        self._http = urllib3.PoolManager()

    def parse(self, html):
        #
        #  Mashape HTML Parser
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all('a'):
            if (tag.get('data-driver') is not None) and \
                    (tag.get('data-driver') == 'explore-api-row-name'):
                self.get_service_information(tag.get('href'))

    def get_service_information(self, link):
        #
        # Obtains service's information
        request = self._http.request('GET', link)
        soup = BeautifulSoup(request.data, 'html.parser')
        service_category = None
        service_description = None
        service_existence = False
        for tag in soup.find_all('h1'):
            if (tag.get('data-driver') is not None) and \
                    (tag.get('data-driver') == 'api-title'):
                service_name = tag.string
                service_existence = True
        if not service_existence:
            return
        for tag in soup.find_all('a'):
            if (tag.get('href') is not None) and \
                    ('/explore?tags=' in tag.get('href')):
                service_category = tag.string
        for tag in soup.find_all('p'):
            if (tag.get('data-driver') is not None) and \
                    (tag.get('data-driver') == 'api-description'):
                service_description = tag.string
        for tag in soup.find_all('script'):
            if tag.string is not None:
                match = re.search('Mashape.Store(.*?).p.mashape.com', tag.string, re.DOTALL)
                if match:
                    endpoint_section_split = match.group(0).split('%22')
                    endpoint = "https://" + endpoint_section_split[len(endpoint_section_split) - 1]
                    break
                else:
                    '''Different pattern'''
                    match = re.search('Mashape.Store(.*?)%22%2C%22targetURL', tag.string, re.DOTALL)
                    if match:
                        endpoint_section_split = match.group(0).split('%22')
                        endpoint = "https://" + endpoint_section_split[len(endpoint_section_split) - 3]
        print endpoint
        service_row = [service_name, service_category, service_description]
        self._data_base_cursor.execute('INSERT INTO services (Name, Category, Description) VALUES (?, ?, ?)',
                                       service_row)
        self._data_base_cursor.execute('SELECT MAX(ID) FROM services')
        service_id = int(self._data_base_cursor.fetchone()[0])
        for tag in soup.find_all('div'):
            if tag.get('data-owner-slug') is not None:
                data_owner_slug = tag.get('data-owner-slug')
                request = None
                while (request is None) or (request.status is not 200):
                    request = self._http.request('GET',
                                                 'https://www.mashape.com/api/internal/' + data_owner_slug + '/apis/' + tag.get(
                                                     'data-api-id') + '/current')
                json_data = json.loads(request.data)
                first = True
                for operation in json_data['endpoints']['data']:
                    if 'response' in operation:
                        operation_row = [operation['name'], operation['method'],
                                         operation['description'] if 'description' in operation else None,
                                         endpoint + operation['route'],
                                         operation['response']['body'] if 'body' in operation['response'] else None,
                                         service_id]
                    else:
                        operation_row = [operation['name'], operation['method'],
                                         operation['description'] if 'description' in operation else None,
                                         endpoint + operation['route'], None, service_id]
                    self._data_base_cursor.execute(
                        'INSERT INTO functions (Name, Method, Description, Endpoint, Response, ServiceID) '
                        'VALUES (?, ?, ?, ?, ?, ?)',
                        operation_row)
                    if first:
                        self._data_base_cursor.execute('SELECT MAX(ID) FROM functions')
                        first = False
                        function_id = int(self._data_base_cursor.fetchone()[0])
                    else:
                        function_id += 1
                    for parameter in operation['routeparameters']['data']:
                        parameter_row = [parameter['name'], parameter['type'],
                                         parameter['description'] if 'description' in parameter else None, function_id]
                        self._data_base_cursor.execute(
                            'INSERT INTO parameters (Name, Type, Description, FunctionID) VALUES (?, ?, ?, ?)',
                            parameter_row)
        self._data_base_connection.commit()

    def __del__(self):
        self._data_base_connection.close()


def main():
    #
    # Main function
    http = urllib3.PoolManager()
    crawler = MashapeCrawler('mashape-dataset.db')
    for i in range(42, SERVICE_AVAILABLE_PAGES):
        print 'Page ' + str(i) + ' from ' + str(SERVICE_AVAILABLE_PAGES - 1)
        request = http.request('GET', 'https://www.mashape.com/explore?page=' + str(i))
        crawler.parse(request.data)


if __name__ == "__main__":
    main()
