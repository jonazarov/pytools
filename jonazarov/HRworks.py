import requests
from urllib.parse import urlparse, parse_qs
from jonazarov.utils import Utils as ut
from types import SimpleNamespace
from typing import List, Iterable

class HRworks:
    def __init__(self, accessKey: str, secretAccessKey: str, languageCode:str='en', cache:bool = True, apiUrl: str = "https://api.hrworks.de/v2/") -> None:
        self.accessKey = accessKey
        self.secretAccessKey = secretAccessKey
        self.apiUrl = apiUrl
        self.languageCode = languageCode
        self.token = self._getToken(cache)

    def _getToken(self, cache:bool = True):
        response = requests.request(
            "POST",
            self.apiUrl + "authentication",
            headers={"Accept": "application/json", "Content-Type": "application/json", "Cache-Control": "only-if-cached" if cache else "no-cache"},
            data=ut.dumps({
                'accessKey': self.accessKey,
                'secretAccessKey': self.secretAccessKey,
            }),
        )
        return ut.loads(response.text).token

    def _apiGet(self, endpoint:str, params:dict={}, cacheSuperssion:bool | None = None) -> dict:
        params['languageCode'] = self.languageCode
        response = requests.request(
            "GET",
            self.apiUrl + endpoint,
            headers={"Accept": "application/json", "Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
            params=params
        )
        result = {}
        result['api'] = ut.loads(response.text)
        if 'link' in response.headers:
            links = response.headers['link'].split(', ')
            for link in links:
                _link = link.split('; rel="')
                result[_link[1][:-1]] = _link[0][1:-1]
        return result
    
    def _params(self, locals) -> dict:
        """Umwandlung der eingehenden Daten in GET-Parameter

        ### Parameter
        * **locals** Eingehende Daten

        ### Rückgabewerte
        * `dict` Daten bereinigt und _ in Keys durch - ersetzt
        """
        params = {}
        for name in locals:
            if name == "self":
                continue
            params[name.replace("_", "-")] = locals[name]
        for name in params:
            if type(params[name]) == bool:
                params[name] = "true" if params[name] else "false"
        return params
    
    def personsMasterData(self, onlyActive: bool = True, persons: List[str] | None = None, usePersonnelNumbers:bool = False) -> Iterable:
        """Returns the current master data of the specified persons.

        ### Arguments
        * **onlyActive `bool` (Default: True)** Set this parameter to false to return persons that have left the company and were set to gone in HRworks as well. Note: Deleted persons cannot be returned as the data was removed from HRworks. This parameter will be ignored if persons are specified directly via the persons parameter.
        * **persons `List[str] | None` optional** The HRworks usernames of the persons to display data for. Note: Using the optional parameter usePersonnelNumbers, HRworks personnel numbers can be passed instead of HRworks usernames.
        * **usePersonnelNumbers `bool` (Default: False)** If set to true, the API will assume the strings in the persons parameter to represent personnel numbers instead of HRworks usernames.
        """
        params = self._params(locals())
        while True:
            result = self._apiGet("persons/master-data", params)
            if not hasattr(result['api'], 'persons'):
                return result['api']
            for person in result['api'].persons:
                yield person
            if not 'next' in result:
                break
            params['page'] = int(parse_qs(urlparse(result['next']).query)['page'][0])