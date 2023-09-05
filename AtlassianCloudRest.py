import requests, time
from bs4 import BeautifulSoup as bs
from typing import List, Callable, Iterable
from functools import cmp_to_key
from requests.auth import HTTPBasicAuth
from jonazarov.utils import Utils as ut
from urllib.parse import urlparse, parse_qs

class objectNotExists(Exception):
    pass

class AtlassianCloud:
    '''
    REST-API for Atlassian-Cloud
    '''
    date_format = "%Y-%m-%dT%H:%M:%S.%fZ"

    def __init__(self, username:str, apikey:str, baseurl:str=None) -> None:
        '''
        REST-Verbindung vorbereiten
        :param username: Benutzername für die Authentifizierung
        :param apikey: API-Key oder Kennwort für die Authentifizierung
        :param base_url OPTIONAL: URL zur Atlassian-Instanz.
        '''
        base_url = ""
        _auth = None
        _api_urls = {}
        _api_version = 1
        self.auth = HTTPBasicAuth(username, apikey)
        if baseurl != None:
            self.setBase(baseurl)

    def setBase(self, baseurl:str) -> None:
        '''
        URL zur Atlassian Instanz setzen.
        :param base_url: URL zur Atlassian-Instanz
        '''
        if baseurl.endswith('/'):
            baseurl = baseurl[:-1]
        self.base_url = baseurl

    def reauth(self, username:str, apikey:str) -> None:
        '''
        Neue Authorisierung vorbereiten
        :param username: Benutzername für die Authentifizierung
        :param apikey: API-Key oder Kennwort für die Authentifizierung
        '''
        self.auth = HTTPBasicAuth(username, apikey)

    def _check(self) -> bool:
        if (self.base_url == ""):
            raise("URL zur Atlassian-Instanz mit setBase() oder bei der Initiierung setzen.")
        
    def _params(self, locals):
        params = {}
        for name in locals:
            if name == 'self': continue
            params[name.replace('_','-')] = locals[name]
        return params
    
    def _callApi(self, call:str, params:dict = None, method = "GET", data:dict = None, apiVersion:int|str = None, alternateBase:str=None):
        '''
        API aufrufen
        :param call: Aufruf der API (Direktive)
        :param params: GET-Parameter
        :param method: HTTP-Methode (GET, POST, PUT, DELETE)
        :param data: Daten-Body
        :param apiVersion: Angabe des API-Endpunktes (in _api_urls gespeichert)
        :param alternateBase: Alternative Base-URL
        '''
        self._check()
        if params != None and 'self' in params and isinstance(self, AtlassianCloud):
            del params['self']
        if data != None and 'self' in data and isinstance(self, AtlassianCloud):
            del data['self']
        headers = {
            "Accept": "application/json"
        }
        return requests.request(
            method,
            (self.base_url if alternateBase == None else alternateBase) + '/' + self._api_urls[apiVersion if apiVersion != None else self._api_version] + call,
            params=params,
            data=ut.dumps(data),
            headers=headers if method in ("GET") else headers | {"Content-Type": "application/json"},
            auth=self.auth
        )

    def _processResponse(self, response:requests.Response, expectedStatusCode:int = 200, noresponse:bool=False, catchCodes:List[int]=None, catchClosure=None):
        '''
        Ergebnis verarbeiten
        :param response: Response-Objekt
        :param expectedStatusCode: Welcher Statuscode erwartet wird
        :param noresponse: Ob ein Antwort-Body erwartet wird (z.B. bei DELETE wird nichts erwartet)
        :param catchCodes: Liste der HHTP-Codes, für die eine Fehlerbehandlung vorgesehen ist.
        :param catchClosure: Funktion (nimmt im ersten Parameter das request-Objekt entgegen) für Fehlerbehandlung
        '''
        try:
            if response.status_code == expectedStatusCode:
                if noresponse or expectedStatusCode == 204:
                    return True
                else:
                    return ut.loads(response.text)
            elif catchCodes != None and catchClosure != None and response.status_code in catchCodes:
                return catchClosure(response)
            else:
                print("API-Fehler")
                print("HTTP-Status:",response.status_code)
                print("Header:",ut.pretty(response.headers))
                print("Content:",response.content.decode('utf-8'))
                print(response.request.method, response.request.url, response.request.body, sep=' | ')
                return None
        except objectNotExists as e:
            raise objectNotExists(e)
        except Exception as e:
            print("Programmfehler:", e)
            return response
        
    def _callSeveralProcessResponse(self, call:str, params:dict = None, method = "GET", data:dict = None, expectedStatusCode:int = 200, noresponse:bool=False, apiVersion:int|str = None, attempt:int = 1):
        '''
        API bei Bedarf mehrfach aufrufen und Ergebnis verarbeiten (für vielfache Aufrufe, für die keine aggregierte Funktion existiert)
        :param call: Aufruf der API (Direktive)
        :param params: GET-Parameter
        :param method: HTTP-Methode (GET, POST, PUT, DELETE)
        :param data: Daten-Body
        :param expectedStatusCode: Welcher Statuscode erwartet wird
        :param noresponse: Ob ein Antwort-Body erwartet wird (z.B. bei DELETE wird nichts erwartet)
        :param apiVersion: Angabe des API-Endpunktes (in _api_urls gespeichert)
        '''
        response = self._callApi(call, params, method, data, apiVersion)
        try:
            if response.status_code == expectedStatusCode:
                if noresponse or expectedStatusCode == 204:
                    return True
                else:
                    return ut.loads(response.text)
            elif response.status_code in (401, 404) and response.content.decode('utf-8') == '{"errorMessage": "Site temporarily unavailable"}' and attempt < 5:
                print('.')
                time.sleep(5)
                return self._callSeveralProcessResponse(call, params, method, data, expectedStatusCode, noresponse, apiVersion, attempt+1)
            else:
                print("API-Fehler")
                print("HTTP-Status:",response.status_code)
                print("Header:",ut.pretty(response.headers))
                print("Content:",response.content.decode('utf-8'))
                print(response.request.method, response.request.url, response.request.body, sep=' | ')
                return None
        except Exception as e:
            print("Programmfehler:", e)
            return response
        
    def _processResponsePaginated(self, call:str, params:dict = None, resultsKey:str="values", subobject:str=None, apiVersion:int|str = None, catchCodes:List[int]=None, catchClosure=None):
        '''
        Ergebnisse seitenweise abrufen
        :param call: API-Call
        :param params: Parameter des API-Calls
        :param resultsKey: In welchem Key werden die Ergebnisse aufgelistet
        :param subobject: Falls angegeben, in welchem Unterobjekt ist das Ergebnis-Array
        :param apiVersion: Angabe des API-Endpunktes (in _api_urls gespeichert)
        :param catchCodes: Liste der HHTP-Codes, für die eine Fehlerbehandlung vorgesehen ist.
        :param catchClosure: Funktion (nimmt im ersten Parameter das request-Objekt entgegen) für Fehlerbehandlung
        '''
        start = 0 if "startAt" not in params else (params["startAt"] if params["startAt"]!= None else 0)
        limit = None if "maxResults" not in params else params["maxResults"]
        results = self._processResponse(self._callApi(call, params, apiVersion=apiVersion), catchCodes=catchCodes, catchClosure=catchClosure)
        if results == None:
            return None
        else:
            resultarray = results if subobject == None else getattr(results, subobject)
            for result in getattr(resultarray, resultsKey):
                yield result
        while results != None and results.startAt+results.maxResults < results.total and (limit == None or results.startAt+results.maxResults < start+limit):
            params["startAt"] = results.startAt+results.maxResults
            if limit != None and params['startAt']+results.maxResults > limit:
                params['maxResults'] = results.maxResults - (params['startAt']+results.maxResults - limit)
            results = self._processResponse(self._callApi(call, params, apiVersion=apiVersion), catchCodes=catchCodes, catchClosure=catchClosure)
            if results == None:
                return None
            else:
                resultarray = results if subobject == None else getattr(results, subobject)
                for result in getattr(resultarray, resultsKey):
                    yield result


class JiraApi(AtlassianCloud):
    def __init__(self, username: str, apikey: str, base_url: str = None) -> None:
        super().__init__(username, apikey, base_url)
        self._api_urls = {
            3: "rest/api/3/",
            2: "rest/api/2/",
            'agile': 'rest/agile/1.0/',
            'greenhopper': 'rest/greenhopper/1.0/',
            'admin': 'secure/admin/'
            }
        self._api_version = 3

    def user(self, accountId:str, expand:str=None):
        '''
        Jira-User ausgeben
        :param accountId: accountId des abgefragten Benutzers
        :param expand: Kommaseparierte Liste aus groups, applicationRoles 
        :return:
        '''
        return self._processResponse(self._callApi("user", locals()))
    
    def userGroups(self, accountId:str):
        '''
        Benutzergruppen zu einem Jira-User ausgeben
        :param accountId: accountId des abgefragten Benutzers
        :return:
        '''
        return self._processResponse(self._callApi("user/groups", locals()))
    
    def groupCreate(self, name:str, withUsersAdd:List[str]=None):
        '''
        Neue Benutzergruppe erzeugen
        :param name: Name der neuen Gruppe
        :param description: Beschreibung der neuen Gruppe
        :param withUsersAdd: Liste der anzufügenden Benutzer (accountId)
        '''
        data = locals()
        del data['withUsersAdd']
        group = self._processResponse(self._callApi("group",method="POST",data=data),201)
        if withUsersAdd:
            for accountId in withUsersAdd:
                self.groupUserAdd(accountId,group.groupId)
        return group
    
    def groupRemove(self, groupId:str=None, groupname:str=None, swapGroupId:str=None, swapGroup:str=None):
        '''
        Benutzergruppe löschen
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        :param swapGroupId: ID der Gruppe, zu der die bestehenden Berechtigungen/Beschränkungen übertragen werden sollen
        :param swapGroup: Name der Gruppe, zu der die bestehenden Berechtigungen/Beschränkungen übertragen werden sollen [deprecated]
        '''
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        params = locals()
        def notFound(r):
            if r.status_code == 400:
                print('FEHLER: ',r.content)
                raise objectNotExists("swapGroup")
            else:
                raise objectNotExists("group")
            
        try:
            return self._processResponse(self._callApi("group",self._params(params),"DELETE"),noresponse=True, catchCodes=[404,400], catchClosure=notFound)
        except objectNotExists:
            return False
        

    def groupSearch(self, query:str=None, excludeId:List[str]=None, exclude:List[str]=None, caseInsensitive:bool=False, maxResults:int=None):
        '''
        Nach Benutzergruppen suchen
        :param query: Zeichenfolge, die im Gruppennamen vorhanden sein muss
        :param excludeId: Liste der Gruppen-IDs, die zu ignorieren sind
        :param exclude: Liste der Gruppen-Namen die zu ignorieren sind [deprecated]
        :param caseInsensitive: Query beachtet keine Groß-/Kleinschreibung
        :param maxResults: Limit der Ergebnisse
        '''
        params = locals()
        return self._processResponse(self._callApi("groups/picker",params))
    
    def groupMember(self, groupId:str=None, groupname:str=None, includeInactiveUsers:bool=False, maxResults:int=None):
        '''
        Mitglieder einer Benutzergruppe ausgeben [Generator]
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        :param includeInactiveUsers: Inaktive Benutzer mit aufzählen
        :param maxResults: Limit für Benutzer-Ergebnis-Liste
        :return: Iterable[Array der Benutzer] oder None, falls Gruppe nicht existiert
        '''
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        def notFound(r):
            raise objectNotExists("group")
        try:
            yield from self._processResponsePaginated("group/member", locals(), catchCodes=[404], catchClosure=notFound)
        except objectNotExists:
            yield None
    
    def groupUserAdd(self, accountId:str, groupId:str=None, groupname:str=None):
        '''
        Benutzer einer Gruppe hinzufügen
        :param accountId: Account-ID des Benutzers, der hinzugefügt werden soll
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        :return: Datensatz der Gruppe (mit aktueller Benutzerliste)
        '''
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        params = locals()
        data = {'accountId':params['accountId']}
        del params['accountId']
        def notFound(r):
            raise objectNotExists("group")
        try:
            return self._processResponse(self._callApi("group/user",self._params(params),"POST",data),201,catchCodes=[400],catchClosure=notFound)
        except objectNotExists:
            return False
    
    def groupUserDel(self, accountId:str, groupId:str=None, groupname:str=None):
        '''
        Benutzer aus einer Gruppe entfernen
        :param accountId: Account-ID des Benutzers, der hinzugefügt werden soll
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        '''
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        params = locals()
        def notFound(r):
            raise objectNotExists("group")
        try:
            return self._processResponse(self._callApi("group/user",self._params(params),"DELETE"),noresponse=True,catchCodes=[404],catchClosure=notFound)
        except objectNotExists:
            return False

    def groupUsersSet(self, setAccountIds:List[str], oldAccountIds:List[str]=None, groupId:str=None, groupname:str=None):
        '''
        Benutzer einer Gruppe setzen
        :param setAccountIds: Account-IDs der Benutzer, die in der Gruppe verbleiben/hinzugefügt werden wollen
        :param oldAccountIds: Account-IDs der aktuellen Benutzer der Gruppe
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        '''
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        if oldAccountIds == None:
            oldAccountIds = [m.accountId for m in list(self.groupMember(groupId, groupname))]
        # neue hinzufügen
        for accountId in setAccountIds:
            if accountId not in oldAccountIds:
                self.groupUserAdd(accountId, groupId, groupname)
        # alte entfernen
        for accountId in oldAccountIds:
            if accountId not in setAccountIds:
                self.groupUserDel(accountId, groupId, groupname)

    def filterMy(self, expand:str=None, includeFavourites:bool=False):
        '''
        Eigene Jira-Filter ausgeben
        :return:
        '''
        return self._processResponse(self._callApi("filter/my", locals()))

    def filterSearch(self, filterName:str=None, accountId:str=None, groupname:str=None, groupId:str=None, projectId:str=None, orderBy:str=None, expand:str=None, overrideSharePermissions:bool=False, startAt:int=None, maxResults:int=None) -> Iterable:
        '''
        Jira-Filter suchen
        https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-filters/#api-rest-api-3-filter-search-get
        :return: Iterable[Array an Filtern]
        '''
        yield from self._processResponsePaginated("filter/search",locals())
        
    def filterGet(self, id):
        '''
        Jira-Filter abrufen
        :param id: ID des Filters
        :return:
        '''
        return self._processResponse(self._callApi(f"filter/{id}"))
        
    def filterUpdate(self, id:int, name:str, jql:str=None, description:str = None, favourite:bool = None, sharePermissions: List[dict] = None, editPermissions: List[dict] = None, expand:str=None, overrideSharePermissions:bool=False):
        '''
        Jira-Filter schreiben
        :param id: ID des Filters
        :param name: Name des Filters
        :param jql: jql des Filters
        :param description: Beschreibung des Filters
        :param favourite: Filter für aktuellen Benutzer als Favoriten markieren
        :param sharePermissions: Betrachtungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        :param editPermissions: Bearbeitungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        '''
        data = locals()
        del data['id'], data['expand'], data['overrideSharePermissions']
        return self._processResponse(self._callApi(f"filter/{id}",{'expand': expand, 'overrideSharePermissions': overrideSharePermissions},"PUT", data))
        
    
    def filterOwner(self, id, accountId):
        '''
        Owner eines Jira-Filters setzen
        :param id: ID des Filters
        :param body: Filter-Daten
        '''
        return self._processResponse(self._callApi(f"filter/{id}/owner",method="PUT", data={"accountId":accountId}), 204)
    

    def agileBoards(self, name:str=None, maxResults:int=None):
        '''
        Sämtliche Software/Agile-Boards auflisten
        :param name: Teilstring des Board-Namens
        '''
        yield from self._processResponsePaginated('board',locals(),apiVersion='agile')

    def agileBoardConfig(self, id:int):
        '''
        Board-Konfiguration auslesen
        :param id: ID des Boards
        '''
        return self._callSeveralProcessResponse(f"rapidviewconfig/editmodel.json?rapidViewId={id}&cardLayoutConfig=false",apiVersion='greenhopper')
    
    def agileBoardAdminSet(self, id:int, userKeys:List[str], groupKeys:List[str]):
        '''
        Board-Konfiguration setzen
        :param id: ID des Boards
        :param userKeys: Liste der Benutzer (accountId)
        :param groupKeys: Liste der Gruppen (accountId)
        '''
        data = {
            'id':id,
            'boardAdmins':{
                'userKeys':userKeys,
                'groupKeys':groupKeys
            }
        }
        return self._callSeveralProcessResponse(f"rapidviewconfig/boardadmins",method="PUT",data=data,apiVersion='greenhopper')

        
    def dashboard(self, filter:str=None, startAt:int=None, maxResults:int=None) -> Iterable:
        '''
        Sämtliche Jira-Dashboards abrufen [Generator]
        :return: Iterable[Array von Dashboard-Objekten]
        '''
        return self._processResponsePaginated("dashboard", locals(), "dashboards")
    
    def dashboardSearch(self, dashboardName:str=None, accountId:str=None, groupname:str=None, groupId:str=None, projectId:str=None, orderBy:str=None, status:str="active", expand:str=None, startAt:int=None, maxResults:int=None):
        '''
        Nach Jira-Dashboards suchen
        :return:
        '''
        return self._processResponsePaginated("dashboard/search", locals())
    
    def dashboardGet(self, id):
        '''
        Jira-Dashboard abrufen
        :param id: ID des Filters
        :return:
        '''
        return self._processResponse(self._callApi(f"dashboard/{id}"))

    def dashboardUpdate(self, id:int, name:str, description:str = None, sharePermissions: List[dict] = None, editPermissions: List[dict] = None):
        '''
        Jira-Dashboard schreiben
        :param id: ID des Dashboards
        :param name: Name des Dashboards
        :param description: Beschreibung des Dashboards
        :param sharePermissions: Betrachtungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        :param editPermissions: Bearbeitungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        '''
        data = locals()
        del data['id']
        return self._processResponse(self._callApi(f"dashboard/{id}",method="PUT", data=data))
    
    def dashboardOwner(self, dashboardId: int, accountId: str):
        '''
        Jira-Dashboard Owner ändern
        :param dashboardId: ID des zu übereignenden Dashboards
        :param accountId: accountId des neuen Eigentümers
        '''
        self._check()
        response1 = requests.get(
            f"{self.base_url}/secure/admin/dashboards/ViewSharedDashboards.jspa",
            auth=self.auth,
        )
        soup = bs(response1.text, "lxml")
        atl_token = soup.find("meta", id="atlassian-token").attrs["content"]
        response = requests.request(
            "POST",
            f"{self.base_url}/secure/admin/dashboards/ChangeSharedDashboardOwner.jspa",
            data={
                "owner": accountId,
                "dashboardId": dashboardId,
                "inline": True,
                "decorator": "dialog",
                "searchName": None,
                "searchOwnerUserName": None,
                "sortColumn": None,
                "sortAscending": None,
                "pagingOffset": None,
                "totalResultCount": None,
                "showTrashList": False,
                "trashSortColumn": None,
                "trashSortAscending": None,
                "trashPagingOffset": None,
                "totalTrashResultCount": -1,
                "returnUrl": "ViewSharedDashboards.jspa",
                "atl_token": atl_token,
            },
            headers={
                "Accept": "text/html, */*; q=0.01",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://smo.atlassian.net",
            },
            cookies=response1.cookies,
            auth=self.auth,
        )
        return self._processResponse(response,noresponse=True)

class ConfluenceApi(AtlassianCloud):
    def __init__(self, username: str, apikey: str, base_url: str = None) -> None:
        super().__init__(username, apikey, base_url)
        self._api_urls = {
            2: "wiki/api/v2/",
            1: "wiki/rest/api/"
        }
        self._api_version = 2

    def _processResponsePaginated(self, call:str, params:dict = None, resultsKey:str="results"):
        limit = None if "limit" not in params else params["limit"]
        if limit == None:
            params["limit"] = 25
        elif limit > 250:
            params["limit"] = 250
        results = self._processResponse(self._callApi(call, params))
        totalCount = 0
        if results == None:
            return None
        else:
            count = len(getattr(results, resultsKey)) # Standard-Seitengröße
            totalCount += count
            for result in getattr(results, resultsKey):
                yield result
        while results != None and hasattr(results._links, 'next')  and (limit == None or totalCount < limit):
            #params['Cursor'] = results._links.next.split('&cursor=')[1] + ';rel="next"'
            try:
                parsed_url = urlparse(results._links.next)
                params['cursor'] = parse_qs(parsed_url.query)['cursor'][0]
            except:
                print("Cursor nicht gefunden! "+results._links.next)
                raise Exception("Cursor nicht gefunden! ")
            if limit != None and totalCount + count > limit:
                params['limit'] = count - (totalCount+count - limit)
            results = self._processResponse(self._callApi(call, params))
            if results == None:
                return None
            else:
                for result in getattr(results, resultsKey):
                    yield result


    def pages(self, id: List[int]=None, title:str=None, status:str=None, body_format:str="storage", limit:str=None, sort:str=None, serialize_ids_as_strings:bool=False):
        '''
        Alle Seiten ausgeben
        :param body_format: storage oder atlas_doc_format
        :return:
        '''
        yield from self._processResponsePaginated("pages",self._params(locals()))

    def labelsPages(self, label:str|int=None, body_format:str="storage", space_id:List[int]=None, limit:str=None, sort:str=None, serialize_ids_as_strings:bool=False) -> Iterable:
        '''
        Alle Seiten zu einem Label ausgeben
        :param label: ID des Labels als int oder Name des Labels als str
        :param body_format: storage oder atlas_doc_format
        :param space_id: IDs der Bereiche, auf die die Ergebnisse ggf. begrenzt werden sollen
        :return: Iterable[Array an Page-Objekten]
        '''
        params = locals()
        del params['label']
        if type(label) is str:
            labelinf = self.labelInformation(label,'page')
            label = labelinf.label.id
        if space_id and isinstance(space_id, list):
            space_id = ','.join([str(n) for n in space_id])
        yield from self._processResponsePaginated(f"labels/{label}/pages",self._params(params))
    
    def pagesChildren(self, id:int, sort:str=None, limit:str=None, serialize_ids_as_strings:bool=False):
        '''
        Alle Unterseiten ausgeben
        :param id: ID der Seite, deren Unterseiten ausgegeben werden sollen
        :param sort: Feldname, nach dem die Ausgabe sortiert werden soll
        :return:
        '''
        params = locals()
        del params['id']
        yield from self._processResponsePaginated(f"pages/{id}/children",self._params(params))

    def pagesSort(self, parentId:int, order:str|Callable="ASC", recursive:bool=False):
        '''
        Seiten eines Zweigs sortieren
        :param parentId: ID der Seite, deren Unterseiten sortiert werden sollen
        :param order: Reihenfolge: ASC= alph. aufsteigend, DESC= alph. absteigend; oder eine Compare-Funktion (mit return 1,0 oder -1), die als Elemente jeweils Dicts mit folgenden Keys bekommt: id, title, status, spaceId, childPosition
        '''
        pages = list(self.pagesChildren(parentId, sort="title"))
        if callable(order):
            pages = sorted(pages, key=cmp_to_key(order))
        for index in range(len(pages)):
            if index < len(pages)-1: # letzte Seite nicht verschieben
                yield (pages[index+1].id, pages[index+1].title, "before" if not callable(order) and order == "DESC" else "after", pages[index].id, pages[index].title, ut.pretty(self.contentMove(pages[index+1].id, "before" if not callable(order) and order == "DESC" else "after", pages[index].id), False, None))
            if recursive:
                yield from self.pagesSort(pages[index].id, order, recursive)

    def pageCreate(self, spaceId:int, title:str=None, parentId:int=None, body:dict|str=None, body_format:str="storage", status:str="current", private:bool=False, embedded:bool=False, serialize_ids_as_strings:bool=False):
        '''
        Seite erzeugen
        :param body: je nach body_format: storage -> HTML/XML; atlas_doc_format -> Inhalt von body.atlas_doc_format.value als dict
        :param body_format: storage oder atlas_doc_format
        :return:
        '''
        data = locals()
        params = {}
        for param in ('private', 'embedded', 'serialize_ids_as_strings'):
            params[param] = data[param]
            del data[param]

        if body_format == "storage":
            data['body'] = {'storage':{
                "representation": "storage",
                "value": data['body']
            }}
        else:
            data['body'] = {"atlas_doc_format": {
                "representation": "atlas_doc_format",
                "value":ut.dumps(data["body"])
            }}
        return self._processResponse(self._callApi(f"pages",self._params(params),"POST",data))

    def pageUpdate(self, id:int, title:str=None, parentId:int=None, body:dict|str=None, body_format:str="storage", status:str="current", version:dict|None=None, serialize_ids_as_strings:bool=False):
        '''
        Seite aktualisieren
        :param id:
        :param body: je nach body_format: storage -> HTML/XML; atlas_doc_format -> Inhalt von body.atlas_doc_format.value als dict
        :param body_format: storage oder atlas_doc_format
        :param version: Version als {'number':<int>,'message':'<string>','minorEdit':<bool>}
        :return:
        '''
        data = locals()
        params = {}
        param = 'serialize_ids_as_strings'
        params[param] = data[param]
        del data[param]

        if body_format == "storage":
            data['body'] = {'storage':{
                "representation": "storage",
                "value": data['body']
            }}
        elif body_format == "atlas_doc_format":
            data['body'] = {"atlas_doc_format": {
                "representation": "atlas_doc_format",
                "value":ut.dumps(data["body"])
            }}
        del data['body_format']
        if version == None:
            page = self.page(id)
            data['version'] = {'number':(int(page.version.number)+1),'message':''}
        return self._processResponse(self._callApi(f"pages/{id}",self._params(params),"PUT",data))

    def page(self, id:int, version:int=None, get_draft:bool=False, body_format:str="storage", serialize_ids_as_strings:bool=False):
        '''
        Einzelne Seite samt Informationen ausgeben
        :param id:
        :param version:
        :param get_draft:
        :param body_format: storage oder atlas_doc_format
        :return:
        '''
        params = locals()
        del params['id']
        return self._processResponse(self._callApi(f"pages/{id}",self._params(params)))
    
    def contentMove(self, pageId:int, position:str,targetId:int):
        '''
        Seite verschieben
        :param pageId: ID der zu verschiebenden Seite
        :param position: Richtung der Verschiebung: before - vor die Ziel-Seite; after - hinter die Ziel-Seite; append - unter die Ziel-Seite (anfügen)
        :param targetId: ID der Ziel-Seite
        :return: pageId
        '''
        return self._processResponse(self._callApi(f"content/{pageId}/move/{position}/{targetId}",method="PUT",apiVersion=1))
    
    def contentDescendants(self, id:int, expand: List[str]=None):
        '''
        Seite verschieben
        :param id:
        :param expand: attachment, comments, page 
        :return: pageId
        '''
        params = locals()
        del params['id']
        return self._processResponse(self._callApi(f"content/{id}/descendant",self._params(params),apiVersion=1))
    
    def labelInformation(self, name:str, type:str=None, start:int=None, limit:int=None):
        '''
        Informationen zum Label abrufen
        :param name: Name des Labels
        :param type: page, blogpost, attachment, page_template
        :param start: Offset für Ausgabe verknüpfter Inhalte
        :para limit: Limit für Ausgabe verknüpfter Inhalte
        '''
        return self._processResponse(self._callApi("label",self._params(locals()),apiVersion=1))
    

class AssetsApi(AtlassianCloud):
    def __init__(self, username: str, apikey: str, base_url: str = None) -> None:
        super().__init__(username, apikey, base_url)
        self._api_version = 1

    def setBase(self, baseurl: str) -> None:
        super().setBase(baseurl)
        response = requests.request(
            'GET',
            f'{self.base_url}/rest/servicedeskapi/assets/workspace',
            auth=self.auth,
            headers={ "Accept": "application/json"}
        )
        if response.status_code == 200:
            workspace = ut.loads(response.text)
            self.workspaceId = workspace.values[0].workspaceId
            self.base_url2 = self.base_url
            self.base_url = f'https://api.atlassian.com/jsm/assets/workspace/{self.workspaceId}/'
            self._api_urls = {
                1: "v1/",
                'assets': f'gateway/api/jsm/assets/workspace/{self.workspaceId}/v1/',
                'insight': f'gateway/api/jsm/insight/workspace/{self.workspaceId}/v1/'
            }
        else:
            raise objectNotExists('WorkspaceID nicht gefunden!')

    def _callDirect(self, call: str, params: dict = None, method="GET", data: dict = None, apiVersion: int | str = None):
        return self._callApi(call, params, method, data, apiVersion, self.base_url2)
    
    def objectschemaList(self, startAt:int=None) -> Iterable:
        '''
        Listet alle Objektschemata auf
        :return: Iterable[Array von Objektschema-Objekten]
        '''
        return self._processResponsePaginated('objectschema/list', locals())
    
    def objectschemaGet(self, id:str):
        '''
        Einzelnes Objektschema aufrufen
        :param id: Objektschema-ID
        :return: Objektschema-Objekt
        '''
        return self._processResponse(self._callApi(f'objectschema/{id}'))

    def objectschemaObjecttypes(self, id:str, excludeAbstract:bool=False):
        '''
        Objekttypen eines Objektschemas auflisten
        :param id: Objektschema-ID
        :param excludeAbstract: Abstrakte Objekttypen ausschließen aus der Auflistung
        :return: Objekt {'entries':[je Objekttyp ein Objekt]}
        '''
        return self._processResponse(self._callApi(f'objectschema/{id}/objecttypes',locals()))
    
    def objectschemaAttributes(self, id:str, query:str="", onlyValueEditable:bool=False, extended:bool=False):
        '''
        Sämtliche Attribute eines Objektschemas auflisten
        :param id: Objektschema-ID
        :param query: Suchausdruck zum Filtern der Ergebnisse anhand des Attribut-Namens
        :param onlyValueEditable: Nur Werte ausgeben, die editierbar sind
        :param extended: In jedem Attribut-Eintrag die Objekttyp-Struktur einbinden, zu der er gehört
        :return: List[Attribut-Objekte]
        '''
        return self._processResponse(self._callApi(f'objectschema/{id}/attributes',locals()))
    
    def objecttypeAttributes(self, id:str, query:str="", onlyValueEditable:bool=False, includeChildren:bool=False, excludeParentAttributes:bool=False, includeValuesExist:bool=False, orderByName:bool=False, orderByRequired:bool=False):
        '''
        Attribute eines Objekttypen auflisten
        :param id: Objekttyp-ID
        :param query: Suchausdruck zum Filtern der Ergebnisse anhand des Attribut-Namens
        :param onlyValueEditable: Nur Werte ausgeben, die editierbar sind
        :return: List[Attribut-Objekte]
        '''
        return self._processResponse(self._callApi(f'objecttype/{id}/attributes'))
    
    def configRoleActors(self, roleId:str):
        '''
        Berechtigte einer Konfigurations-Rolle (Object Schema Users/Developers/Managers) abrufen
        :param id: ID der Konfigurations-Rolle
        :return: {'id':id, 'actors':[Objekt je Berechtigten], ...}
        '''
        return self._processResponse(self._callDirect(f'config/role/{roleId}',apiVersion='insight'))
    
    def configRoleObjectschema(self, id:str):
        '''
        Konfigurations-Rollen eines Objektschemas abrufen
        :param id: Objectschema-ID
        :return: {'Object Schema Users/Developers/Managers':{'id':id, 'actors':[Objekt je Berechtigten], ...}}
        '''
        roles = ut.normalize(self._processResponse(self._callDirect(f'config/role/objectschema/{id}',apiVersion='assets')))
        for role in roles:
            roles[role] = self.configRoleActors(roles[role].split('/')[-1])
        return roles
    
    def configRoleObjecttype(self, id:str):
        '''
        Konfigurations-Rollen eines Objekttypen abrufen
        :param id: Objekttyp-ID
        :return: {'Object Schema Users/Developers/Managers':{'id':id, 'actors':[Objekt je Berechtigten], ...}}
        '''
        roles = ut.normalize(self._processResponse(self._callDirect(f'config/role/objecttype/{id}',apiVersion='assets')))
        for role in roles:
            roles[role] = self.configRoleActors(roles[role].split('/')[-1])
        return roles
    
    def configRoleUpdate(self, roleId:str=None, userActors:List[str]=[], groupActors:List[str]=[]):
        '''
        Konfigurations-Rollen aktualisieren
        :param roleId: Konfigurations-Rollen-ID
        :param userActors: Liste der accountIds
        :param groupActors: Liste der Gruppen-Namen
        :return: {'id':id, 'actors':[Objekt je Berechtigten], ...}
        '''
        data = {
            'id': roleId,
            'categorisedActors': {
                'atlassian-group-role-actor' : groupActors,
                'atlassian-user-role-actor' : userActors,
            }
        }
        return self._processResponse(self._callDirect(f'config/role/{roleId}',method='PUT',data=data,apiVersion='assets'))