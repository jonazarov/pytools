import requests, time
from typing import List, Callable
from functools import cmp_to_key
from requests.auth import HTTPBasicAuth
from jonazarov.utils import Utils as ut
from urllib.parse import urlparse, parse_qs

class AtlassianCloud:
    """
    REST-API for Atlassian-Cloud
    """
    date_format = "%Y-%m-%dT%H:%M:%S.%fZ"

    def __init__(self, username:str, apikey:str, baseurl:str=None) -> None:
        """
        REST-Verbindung vorbereiten
        :param username: Benutzername für die Authentifizierung
        :param apikey: API-Key oder Kennwort für die Authentifizierung
        :param base_url OPTIONAL: URL zur Atlassian-Instanz.
        """
        base_url = ""
        _auth = None
        _api_urls = {}
        _api_version = 1
        if baseurl != None:
            self.setBase(baseurl)
        self.auth = HTTPBasicAuth(username, apikey)

    def setBase(self, baseurl:str) -> None:
        """
        URL zur Atlassian Instanz setzen.
        :param base_url: URL zur Atlassian-Instanz
        """
        if baseurl.endswith('/'):
            baseurl = baseurl[:-1]
        self.base_url = baseurl

    def reauth(self, username:str, apikey:str) -> None:
        """
        Neue Authorisierung vorbereiten
        :param username: Benutzername für die Authentifizierung
        :param apikey: API-Key oder Kennwort für die Authentifizierung
        """
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
    
    def _callApi(self, call:str, params:dict = None, method = "GET", data:dict = None, apiVersion:int|str = None):
        """
        API aufrufen
        :param call: Aufruf der API (Direktive)
        :param params: GET-Parameter
        :param method: HTTP-Methode (GET, POST, PUT, DELETE)
        :param data: Daten-Body
        :param apiVersion: Angabe des API-Endpunktes (in _api_urls gespeichert)
        """
        self._check()
        if params != None and 'self' in params and isinstance(self, AtlassianCloud):
            del params['self']
        if data != None and 'self' in data and isinstance(self, AtlassianCloud):
            del data['self']
        headers = {
            "Accept": "application/json"
        }
        if type(data) is dict:
            for key in dict(data):
                if data[key] == None:
                    del data[key]
        return requests.request(
            method,
            self.base_url + '/' + self._api_urls[apiVersion if apiVersion != None else self._api_version] + call,
            params=params,
            data=ut.dumps(data),
            headers=headers if method in ("GET") else headers | {"Content-Type": "application/json"},
            auth=self.auth
        )

    def _processResponse(self, response:requests.Response, expectedStatusCode:int = 200, noresponse:bool=False):
        """
        Ergebnis verarbeiten
        :param response: Response-Objekt
        :param expectedStatusCode: Welcher Statuscode erwartet wird
        :param noresponse: Ob ein Antwort-Body erwartet wird (z.B. bei DELETE wird nichts erwartet)
        """
        try:
            if response.status_code == expectedStatusCode:
                if noresponse or expectedStatusCode == 204:
                    return True
                else:
                    return ut.loads(response.text)
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
        
    def _callSeveralProcessResponse(self, call:str, params:dict = None, method = "GET", data:dict = None, expectedStatusCode:int = 200, noresponse:bool=False, apiVersion:int|str = None, attempt:int = 1):
        """
        API bei Bedarf mehrfach aufrufen und Ergebnis verarbeiten (für vielfache Aufrufe, für die keine aggregierte Funktion existiert)
        :param call: Aufruf der API (Direktive)
        :param params: GET-Parameter
        :param method: HTTP-Methode (GET, POST, PUT, DELETE)
        :param data: Daten-Body
        :param expectedStatusCode: Welcher Statuscode erwartet wird
        :param noresponse: Ob ein Antwort-Body erwartet wird (z.B. bei DELETE wird nichts erwartet)
        :param apiVersion: Angabe des API-Endpunktes (in _api_urls gespeichert)
        """
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


class JiraApi(AtlassianCloud):
    def __init__(self, username: str, apikey: str, base_url: str = None) -> None:
        super().__init__(username, apikey, base_url)
        self._api_urls = {
            3: "rest/api/3/",
            2: "rest/api/2/",
            'agile': 'rest/agile/1.0/',
            'greenhopper': 'rest/greenhopper/1.0/'
            }
        self._api_version = 3

    def _processResponsePaginated(self, call:str, params:dict = None, resultsKey:str="values", subobject:str=None, apiVersion:int|str = None):
        """
        Ergebnisse seitenweise abrufen
        :param call: API-Call
        :param params: Parameter des API-Calls
        :param resultsKey: In welchem Key werden die Ergebnisse aufgelistet
        :param subobject: Falls angegeben, in welchem Unterobjekt ist das Ergebnis-Array
        :param apiVersion: Angabe des API-Endpunktes (in _api_urls gespeichert)
        """
        start = 0 if "startAt" not in params else (params["startAt"] if params["startAt"]!= None else 0)
        limit = None if "maxResults" not in params else params["maxResults"]
        results = self._processResponse(self._callApi(call, params, apiVersion=apiVersion))
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
            results = self._processResponse(self._callApi(call, params, apiVersion=apiVersion))
            if results == None:
                return None
            else:
                resultarray = results if subobject == None else getattr(results, subobject)
                for result in getattr(resultarray, resultsKey):
                    yield result


    def user(self, accountId:str, expand:str=None):
        """
        Jira-User ausgeben
        :param accountId: accountId des abgefragten Benutzers
        :param expand: Kommaseparierte Liste aus groups, applicationRoles 
        :return:
        """
        return self._processResponse(self._callApi("user", locals()))
    
    def userGroups(self, accountId:str):
        """
        Benutzergruppen zu einem Jira-User ausgeben
        :param accountId: accountId des abgefragten Benutzers
        :return:
        """
        return self._processResponse(self._callApi("user/groups", locals()))
    
    def groupCreate(self, name:str, withUsersAdd:List[str]=None):
        """
        Neue Benutzergruppe erzeugen
        :param name: Name der neuen Gruppe
        :param description: Beschreibung der neuen Gruppe
        :param withUsersAdd: Liste der anzufügenden Benutzer (accountId)
        """
        data = locals()
        del data['withUsersAdd']
        group = self._processResponse(self._callApi("group",method="POST",data=data),201)
        if len(withUsersAdd)>0:
            for accountId in withUsersAdd:
                self.groupUserAdd(accountId,group.groupId)
        return group
    
    def groupRemove(self, groupId:str=None, groupname:str=None, swapGroupId:str=None, swapGroup:str=None):
        """
        Benutzergruppe löschen
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        :param swapGroupId: ID der Gruppe, zu der die bestehenden Berechtigungen/Beschränkungen übertragen werden sollen
        :param swapGroup: Name der Gruppe, zu der die bestehenden Berechtigungen/Beschränkungen übertragen werden sollen [deprecated]
        """
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        params = locals()
        return self._processResponse(self._callApi("group",self._params(params),"DELETE"),noresponse=True)
        

    def groupSearch(self, query:str=None, excludeId:List[str]=None, exclude:List[str]=None, caseInsensitive:bool=False, maxResults:int=None):
        """"
        Nach Benutzergruppen suchen
        :param query: Zeichenfolge, die im Gruppennamen vorhanden sein muss
        :param excludeId: Liste der Gruppen-IDs, die zu ignorieren sind
        :param exclude: Liste der Gruppen-Namen die zu ignorieren sind [deprecated]
        :param caseInsensitive: Query beachtet keine Groß-/Kleinschreibung
        :param maxResults: Limit der Ergebnisse
        """
        params = locals()
        return self._processResponse(self._callApi("groups/picker",params))
    
    def groupMember(self, groupId:str=None, groupname:str=None, includeInactiveUsers:bool=False, maxResults:int=None):
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        """
        Mitglieder einer Benutzergruppe ausgeben
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        :param includeInactiveUsers: Inaktive Benutzer mit aufzählen
        :param maxResults: Limit für Benutzer-Ergebnis-Liste
        :return:
        """
        yield from self._processResponsePaginated("group/member", locals())
    
    def groupUserAdd(self, accountId:str, groupId:str=None, groupname:str=None):
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        """
        Mitglieder einer Benutzergruppe ausgeben
        :param accountId: Account-ID des Benutzers, der hinzugefügt werden soll
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        :return:
        """
        params = locals()
        data = {'accountId':params['accountId']}
        del params['accountId']
        return self._processResponse(self._callApi("group/user",self._params(params),"POST",data),201)
    
    def groupUserDel(self, accountId:str, groupId:str=None, groupname:str=None):
        if groupId == None and groupname == None:
            raise ValueError('groupId oder groupname sollen gesetzt sein')
        """
        Mitglieder einer Benutzergruppe ausgeben
        :param accountId: Account-ID des Benutzers, der hinzugefügt werden soll
        :param groupId: ID der Gruppe
        :param groupname: Name der Gruppe [deprecated]
        :return:
        """
        params = locals()
        return self._processResponse(self._callApi("group/user",self._params(params),"DELETE"),noresponse=True)


    def filterMy(self, expand:str=None, includeFavourites:bool=False):
        """
        Eigene Jira-Filter ausgeben
        :return:
        """
        return self._processResponse(self._callApi("filter/my", locals()))

    def filterSearch(self, filterName:str=None, accountId:str=None, groupname:str=None, groupId:str=None, projectId:str=None, orderBy:str=None, expand:str=None, overrideSharePermissions:bool=False, startAt:int=None, maxResults:int=None):
        """
        Jira-Filter suchen
        https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-filters/#api-rest-api-3-filter-search-get
        :return: 
        """
        yield from self._processResponsePaginated("filter/search",locals())
        
    def filterGet(self, id):
        """
        Jira-Filter abrufen
        :param id: ID des Filters
        :return:
        """
        return self._processResponse(self._callApi(f"filter/{id}"))
        
    def filterUpdate(self, id:int, name:str, jql:str=None, description:str = None, favourite:bool = None, sharePermissions: List[dict] = None, editPermissions: List[dict] = None, expand:str=None, overrideSharePermissions:bool=False):
        """
        Jira-Filter schreiben
        :param id: ID des Filters
        :param name: Name des Filters
        :param jql: jql des Filters
        :param description: Beschreibung des Filters
        :param favourite: Filter für aktuellen Benutzer als Favoriten markieren
        :param sharePermissions: Betrachtungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        :param editPermissions: Bearbeitungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        """
        data = locals()
        del data['id'], data['expand'], data['overrideSharePermissions']
        return self._processResponse(self._callApi(f"filter/{id}",{'expand': expand, 'overrideSharePermissions': overrideSharePermissions},"PUT", data))
        
    
    def filterOwner(self, id, accountId):
        """
        Owner eines Jira-Filters setzen
        :param id: ID des Filters
        :param body: Filter-Daten
        """
        return self._processResponse(self._callApi(f"filter/{id}/owner",method="PUT", data={"accountId":accountId}), 204)
    

    def agileBoards(self, name:str=None, maxResults:int=None):
        """
        Sämtliche Software/Agile-Boards auflisten
        :param name: Teilstring des Board-Namens
        """
        yield from self._processResponsePaginated('board',locals(),apiVersion='agile')

    def agileBoardConfig(self, id:int):
        """
        Board-Konfiguration auslesen
        :param id: ID des Boards
        """
        return self._callSeveralProcessResponse(f"rapidviewconfig/editmodel.json?rapidViewId={id}&cardLayoutConfig=false",apiVersion='greenhopper')

        
    def dashboard(self, filter:str=None, startAt:int=None, maxResults:int=None):
        """
        Sämtliche Jira-Dashboards abrufen
        :return:
        """
        return self._processResponsePaginated("dashboard", locals(), "dashboards")
    
    def dashboardSearch(self, dashboardName:str=None, accountId:str=None, groupname:str=None, groupId:str=None, projectId:str=None, orderBy:str=None, status:str="active", expand:str=None, startAt:int=None, maxResults:int=None):
        """
        Nach Jira-Dashboards suchen
        :return:
        """
        return self._processResponsePaginated("dashboard/search", locals())
    
    def dashboardGet(self, id):
        """
        Jira-Dashboard abrufen
        :param id: ID des Filters
        :return:
        """
        return self._processResponse(self._callApi(f"dashboard/{id}"))

    def dashboardUpdate(self, id:int, name:str, description:str = None, sharePermissions: List[dict] = None, editPermissions: List[dict] = None):
        """
        Jira-Dashboard schreiben
        :param id: ID des Dashboards
        :param name: Name des Dashboards
        :param description: Beschreibung des Dashboards
        :param sharePermissions: Betrachtungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        :param editPermissions: Bearbeitungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        """
        data = locals()
        del data['id']
        return self._processResponse(self._callApi(f"dashboard/{id}",method="PUT", data=data))
    

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
        """
        Alle Seiten ausgeben
        :param body_format: storage oder atlas_doc_format
        :return:
        """
        yield from self._processResponsePaginated("pages",self._params(locals()))

    def labelsPages(self, label:str|int=None, body_format:str="storage", limit:str=None, sort:str=None, serialize_ids_as_strings:bool=False):
        """
        Alle Seiten zu einem Label ausgeben
        :param label: ID des Labels als int oder Name des Labels als str
        :param body_format: storage oder atlas_doc_format
        :return:
        """
        params = locals()
        del params['label']
        if type(label) is str:
            labelinf = self.labelInformation(label,'page')
            label = labelinf.label.id
        yield from self._processResponsePaginated(f"labels/{label}/pages",self._params(params))
    
    def pagesChildren(self, id:int, sort:str=None, limit:str=None, serialize_ids_as_strings:bool=False):
        """
        Alle Unterseiten ausgeben
        :param id: ID der Seite, deren Unterseiten ausgegeben werden sollen
        :param sort: Feldname, nach dem die Ausgabe sortiert werden soll
        :return:
        """
        params = locals()
        del params['id']
        yield from self._processResponsePaginated(f"pages/{id}/children",self._params(params))

    def pagesSort(self, parentId:int, order:str|Callable="ASC", recursive:bool=False):
        """
        Seiten eines Zweigs sortieren
        :param parentId: ID der Seite, deren Unterseiten sortiert werden sollen
        :param order: Reihenfolge: ASC= alph. aufsteigend, DESC= alph. absteigend; oder eine Compare-Funktion (mit return 1,0 oder -1), die als Elemente jeweils Dicts mit folgenden Keys bekommt: id, title, status, spaceId, childPosition
        """
        pages = list(self.pagesChildren(parentId, sort="title"))
        if callable(order):
            pages = sorted(pages, key=cmp_to_key(order))
        for index in range(len(pages)):
            if index < len(pages)-1: # letzte Seite nicht verschieben
                yield (pages[index+1].id, pages[index+1].title, "before" if not callable(order) and order == "DESC" else "after", pages[index].id, pages[index].title, ut.pretty(self.contentMove(pages[index+1].id, "before" if not callable(order) and order == "DESC" else "after", pages[index].id), False, None))
            if recursive:
                yield from self.pagesSort(pages[index].id, order, recursive)

    def pageCreate(self, spaceId:int, title:str=None, parentId:int=None, body:dict|str=None, body_format:str="storage", status:str="current", private:bool=False, embedded:bool=False, serialize_ids_as_strings:bool=False):
        """
        Seite erzeugen
        :param body: je nach body_format: storage -> HTML/XML; atlas_doc_format -> Inhalt von body.atlas_doc_format.value als dict
        :param body_format: storage oder atlas_doc_format
        :return:
        """
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
        """
        Seite aktualisieren
        :param id:
        :param body: je nach body_format: storage -> HTML/XML; atlas_doc_format -> Inhalt von body.atlas_doc_format.value als dict
        :param body_format: storage oder atlas_doc_format
        :param version: Version als {'number':<int>,'message':'<string>','minorEdit':<bool>}
        :return:
        """
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
        """
        Einzelne Seite samt Informationen ausgeben
        :param id:
        :param version:
        :param get_draft:
        :param body_format: storage oder atlas_doc_format
        :return:
        """
        params = locals()
        del params['id']
        return self._processResponse(self._callApi(f"pages/{id}",self._params(params)))
    
    def contentMove(self, pageId:int, position:str,targetId:int):
        """
        Seite verschieben
        :param pageId: ID der zu verschiebenden Seite
        :param position: Richtung der Verschiebung: before - vor die Ziel-Seite; after - hinter die Ziel-Seite; append - unter die Ziel-Seite (anfügen)
        :param targetId: ID der Ziel-Seite
        :return: pageId
        """
        return self._processResponse(self._callApi(f"content/{pageId}/move/{position}/{targetId}",method="PUT",apiVersion=1))
    
    def contentDescendants(self, id:int, expand: List[str]=None):
        """
        Seite verschieben
        :param id:
        :param expand: attachment, comments, page 
        :return: pageId
        """
        params = locals()
        del params['id']
        return self._processResponse(self._callApi(f"content/{id}/descendant",self._params(params),apiVersion=1))
    
    def labelInformation(self, name:str, type:str=None, start:int=None, limit:int=None):
        """
        Informationen zum Label abrufen
        :param name: Name des Labels
        :param type: page, blogpost, attachment, page_template
        :param start: Offset für Ausgabe verknüpfter Inhalte
        :para limit: Limit für Ausgabe verknüpfter Inhalte
        """
        return self._processResponse(self._callApi("label",self._params(locals()),apiVersion=1))
    
