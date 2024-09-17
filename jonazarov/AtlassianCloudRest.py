import requests, time, re
from bs4 import BeautifulSoup as bs
from typing import List, Callable, Iterable
from types import SimpleNamespace
from functools import cmp_to_key
from requests.auth import HTTPBasicAuth
from jonazarov.utils import Utils as ut
from urllib.parse import urlparse, parse_qs
from prompt_toolkit.shortcuts import message_dialog


def loadAtlassianAuth(configfile: str | None = None, seperateJC: bool = False) -> SimpleNamespace:
    """Lädt die Konfiguration aus der Konfigurationsdatei mithilfe einer Standard-Definition und versucht einen Login an der REST-API

    ### Parameter
    * **configfile `str | None` (default None)** Dateiname der Konfigurationsdatei. Wenn nichts angegeben, wird nach _config.json_ im Verzeichnis des aufrufenden Skripts gesucht
    * **seperateJC `bool` (Default False)** base-URLs zwischen Jira und Confluence separat speichern

    ### Rückgabewerte
    * `SimpleNamespace` Ausgelesene, normalisierte Konfiguration
    """
    if not seperateJC:
        config_base_urls = "Bitte Cloud-Instanzen durch Kommata getrennt eingeben (Subdomains ausreichend):"
    else:
        config_base_urls = {
            "confluence": "Bitte Cloud-Instanzen für Confluence durch Kommata getrennt eingeben (Subdomains ausreichend):",
            "jira": "Bitte Cloud-Instanzen für Jira durch Kommata getrennt eingeben (Subdomains ausreichend):",
        }
    config = ut.getconfig(
        {
            "base_urls": config_base_urls,
            "orgadmin": {
                "user": "Bitte Benutzernamen des Admins eingeben:",
                "token": "Bitte API-Token des Admins eingeben:",
            },
        },
        configfile,
    )

    def baseurl_normalize(base_urls: str | List[str]) -> List[str] | None:
        """Atlassian-URLs normalisieren

        ### Parameter
        * **base_urls `str`** Eingangs-URLs

        ### Rückgabewert
        * `dict | List[str] | None`
        """
        if type(base_urls) is str:
            base_urls = base_urls.split(",")
        for i in range(len(base_urls)):
            url = base_urls[i]
            url = url.strip().replace("https://", "").replace("http://", "").replace(".atlassian.net/", "").replace(".atlassian.net", "")
            if not re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?$", url):
                base_urls[i] = None
            else:
                base_urls[i] = f"https://{url}.atlassian.net/"
        base_urls = [url for url in base_urls if url]
        if not len(base_urls):
            return None
        return base_urls
        
    retry = False
    if not seperateJC:
        config.base_urls = baseurl_normalize(config.base_urls)
        if config.base_urls == None:
            delattr(config, 'base_urls')
            retry = True
    else:
        config.base_urls = ut.normalize(config.base_urls)
        for dest in config.base_urls:
            config.base_urls[dest] = baseurl_normalize(config.base_urls[dest])
            if config.base_urls[dest] == None:
                del config.base_urls[dest]
                retry = True
        config.base_urls = ut.simplifize(config.base_urls)

    ut.setconfig(config)
    if retry:
        return loadAtlassianAuth(configfile)

    if not seperateJC:
        jira = JiraApi(config.orgadmin.user, config.orgadmin.token, config.base_urls[0])
    else:
        jira = JiraApi(config.orgadmin.user, config.orgadmin.token, config.base_urls.jira[0])
    try:
        u = jira.usersGetByName(config.orgadmin.user)
        if u == []:
            message_dialog("Fehler bei der Authentifizierung", "Die angegebenen Authentifizierungsdaten scheinen ungültig zu sein! Bitte Eingaben wiederholen!", "OK", ut.pt_style).run()
            config = ut.normalize(config)
            del config["orgadmin"]
            ut.setconfig(config)
            return loadAtlassianAuth(configfile)
    except objectNotExists as e:
        message_dialog("Fehler bei der Anmeldung", "Die angegebene Cloud-Instanz kann nicht erreicht werden! Bitte Eingaben wiederholen!", "OK", ut.pt_style).run()
        config = ut.normalize(config)
        del config["base_urls"]
        ut.setconfig(config)
        return loadAtlassianAuth(configfile)
    _config = ut.normalize(config)
    _config["orgadmin"]["accountId"] = u[0].accountId
    config = ut.simplifize(_config)
    ut.setconfig(config)
    return config


class objectNotExists(Exception):
    pass


class AtlassianCloud:
    """
    REST-API for Atlassian-Cloud
    """

    date_format = "%Y-%m-%dT%H:%M:%S.%fZ"

    def __init__(self, username: str, apikey: str, baseurl: str | None = None) -> None:
        """
        REST-Verbindung vorbereiten
        ### Parameter
        * **username `str`** Benutzername für die Authentifizierung
        * **apikey `str`** API-Key oder Kennwort für die Authentifizierung
        * **base_url `str | None`(Default None)** URL zur Atlassian-Instanz.
        """
        base_url = ""
        _auth = None
        _api_urls = {}
        _api_version = 1
        self.auth = HTTPBasicAuth(username, apikey)
        if baseurl != None:
            self.setBase(baseurl)

    def setBase(self, baseurl: str) -> None:
        """
        URL zur Atlassian Instanz setzen.
        ### Parameter
        * **base_url `str`** URL zur Atlassian-Instanz
        """
        if baseurl.endswith("/"):
            baseurl = baseurl[:-1]
        self.base_url = baseurl

    def reauth(self, username: str, apikey: str) -> None:
        """
        Neue Authorisierung vorbereiten
        ### Rückgabewerte
        * **username `str`** Benutzername für die Authentifizierung
        * **apikey `str`** API-Key oder Kennwort für die Authentifizierung
        """
        self.auth = HTTPBasicAuth(username, apikey)

    def _check(self):
        """Sicherheitsüberprüfung, ob Eigenschaft `base_url`gesetzt ist (ansonsten Fehler)"""
        if self.base_url == "":
            raise ("URL zur Atlassian-Instanz mit setBase() oder bei der Initiierung setzen.")

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
        return params

    def _callGui(self, url: str):
        """GUI aufrufen
        ### Parameter
        * **url `str`** URL zur GUI (nach Base-URL)
        ### Rückgabewerte
        * Im Erfolgsfall ein beautiful-soap Objekt, andernfalls None; dazu das response-Objekt
        """
        self._check()
        response = requests.get(
            f"{self.base_url}/{url}",
            auth=self.auth,
        )
        if response.status_code == 200:
            return bs(response.text, "lxml"), response
        else:
            return None, response

    def _callApi(
        self,
        call: str,
        params: dict | None = None,
        method: str = "GET",
        data: dict | None = None,
        apiVersion: int | str | None = None,
        alternateBase: str | None = None,
    ):
        """
        API aufrufen
        ### Rückgabewerte
        * **call `str`** Aufruf der API (Direktive)
        * **params `dict | None` (Default None)** GET-Parameter
        * **method `str` (Default "GET")** HTTP-Methode (GET, POST, PUT, DELETE)
        * **data `dict | None` (Default None)** Daten-Body
        * **apiVersion `int | str | None` (Default None)** Angabe des API-Endpunktes (in _api_urls gespeichert)
        * **alternateBase `str | None` (Default None)** Alternative Base-URL
        """
        self._check()
        if params != None and "self" in params and isinstance(self, AtlassianCloud):
            del params["self"]
        if data != None and "self" in data and isinstance(self, AtlassianCloud):
            del data["self"]
        headers = {"Accept": "application/json"}
        return requests.request(
            method,
            (self.base_url if alternateBase == None else alternateBase) + "/" + self._api_urls[apiVersion if apiVersion != None else self._api_version] + call,
            params=params,
            data=ut.dumps(data),
            headers=(headers if method in ("GET") else headers | {"Content-Type": "application/json"}),
            auth=self.auth,
        )

    def _processResponse(
        self,
        response: requests.Response,
        expectedStatusCode: int = 200,
        noresponse: bool = False,
        catchCodes: List[int] = None,
        catchClosure=None,
    ):
        """
        Ergebnis verarbeiten
        ### Rückgabewerte
        * **response** Response-Objekt
        * **expectedStatusCode** Welcher Statuscode erwartet wird
        * **noresponse** Ob ein Antwort-Body erwartet wird (z.B. bei DELETE wird nichts erwartet)
        * **catchCodes** Liste der HHTP-Codes, für die eine Fehlerbehandlung vorgesehen ist.
        * **catchClosure** Funktion (nimmt im ersten Parameter das request-Objekt entgegen) für Fehlerbehandlung
        """
        try:
            if response.status_code == expectedStatusCode:
                if noresponse or expectedStatusCode == 204:
                    return True
                else:
                    return ut.loads(response.text)
            elif catchCodes != None and catchClosure != None and response.status_code in catchCodes:
                return catchClosure(response)
            elif catchCodes != None and response.status_code in catchCodes:
                raise objectNotExists()
            else:
                print("API-Fehler")
                print("HTTP-Status:", response.status_code)
                print("Header:", ut.pretty(response.headers))
                print("Content:", response.content.decode("utf-8"))
                print(
                    response.request.method,
                    response.request.url,
                    response.request.body,
                    sep=" | ",
                )
                return None
        except objectNotExists as e:
            raise objectNotExists(e)
        except Exception as e:
            print("Programmfehler:", e)
            return response

    def _callSeveralProcessResponse(
        self,
        call: str,
        params: dict = None,
        method="GET",
        data: dict = None,
        expectedStatusCode: int = 200,
        noresponse: bool = False,
        apiVersion: int | str = None,
        attempt: int = 1,
    ):
        """
        API bei Bedarf mehrfach aufrufen und Ergebnis verarbeiten (für vielfache Aufrufe, für die keine aggregierte Funktion existiert)
        * **call** Aufruf der API (Direktive)
        * **params** GET-Parameter
        * **method** HTTP-Methode (GET, POST, PUT, DELETE)
        * **data** Daten-Body
        * **expectedStatusCode** Welcher Statuscode erwartet wird
        * **noresponse** Ob ein Antwort-Body erwartet wird (z.B. bei DELETE wird nichts erwartet)
        * **apiVersion** Angabe des API-Endpunktes (in _api_urls gespeichert)
        """
        response = self._callApi(call, params, method, data, apiVersion)
        try:
            if response.status_code == expectedStatusCode:
                if noresponse or expectedStatusCode == 204:
                    return True
                else:
                    return ut.loads(response.text)
            elif response.status_code in (401, 404) and response.content.decode("utf-8") == '{"errorMessage": "Site temporarily unavailable"}' and attempt < 5:
                print(".")
                time.sleep(5)
                return self._callSeveralProcessResponse(
                    call,
                    params,
                    method,
                    data,
                    expectedStatusCode,
                    noresponse,
                    apiVersion,
                    attempt + 1,
                )
            else:
                print("API-Fehler")
                print("HTTP-Status:", response.status_code)
                print("Header:", ut.pretty(response.headers))
                print("Content:", response.content.decode("utf-8"))
                print(
                    response.request.method,
                    response.request.url,
                    response.request.body,
                    sep=" | ",
                )
                return None
        except Exception as e:
            print("Programmfehler:", e)
            return response

    def _processResponsePaginated(
        self,
        call: str,
        params: dict = None,
        resultsKey: str = "values",
        subobject: str = None,
        apiVersion: int | str = None,
        catchCodes: List[int] = None,
        catchClosure=None,
        method: str = "GET",
        data: dict = None,
    ):
        """
        Ergebnisse seitenweise abrufen
        ### Rückgabewerte
        * **call** API-Call
        * **params** Parameter des API-Calls
        * **resultsKey** In welchem Key werden die Ergebnisse aufgelistet
        * **subobject** Falls angegeben, in welchem Unterobjekt ist das Ergebnis-Array
        * **apiVersion** Angabe des API-Endpunktes (in _api_urls gespeichert)
        * **catchCodes** Liste der HHTP-Codes, für die eine Fehlerbehandlung vorgesehen ist.
        * **catchClosure** Funktion (nimmt im ersten Parameter das request-Objekt entgegen) für Fehlerbehandlung
        * **method** HTTP-Methode
        * **data** Request-Body
        """
        start = 0 if "startAt" not in params else (params["startAt"] if params["startAt"] != None else 0)
        limit = None if "maxResults" not in params else params["maxResults"]
        results = self._processResponse(
            self._callApi(call, params, apiVersion=apiVersion, method=method, data=data),
            catchCodes=catchCodes,
            catchClosure=catchClosure,
        )
        if results == None:
            return None
        else:
            resultarray = results if subobject == None else getattr(results, subobject)
            for result in getattr(resultarray, resultsKey):
                yield result
        while results != None and results.startAt + results.maxResults < results.total and (limit == None or results.startAt + results.maxResults < start + limit):
            params["startAt"] = results.startAt + results.maxResults
            if limit != None and params["startAt"] + results.maxResults > limit:
                params["maxResults"] = results.maxResults - (params["startAt"] + results.maxResults - limit)
            results = self._processResponse(
                self._callApi(call, params, apiVersion=apiVersion, method=method, data=data),
                catchCodes=catchCodes,
                catchClosure=catchClosure,
            )
            if results == None:
                return None
            else:
                resultarray = results if subobject == None else getattr(results, subobject)
                for result in getattr(resultarray, resultsKey):
                    yield result

    def _notFoundStatus(r):
        if r.status_code == 404:
            return None


class JiraApi(AtlassianCloud):
    def __init__(self, username: str, apikey: str, base_url: str = None) -> None:
        super().__init__(username, apikey, base_url)
        self._api_urls = {
            3: "rest/api/3/",
            2: "rest/api/2/",
            "agile": "rest/agile/1.0/",
            "greenhopper": "rest/greenhopper/1.0/",
            "admin": "secure/admin/",
        }
        self._api_version = 3

    def user(self, accountId: str, expand: str = None):
        """
        Jira-User ausgeben
        * **accountId** accountId des abgefragten Benutzers
        * **expand** Kommaseparierte Liste aus groups, applicationRoles
        ### Rückgabewerte
        * 
        """
        return self._processResponse(self._callApi("user", locals()))

    def userSearch(self, accountId: str = None, query: str = None):
        """
        Nach Jira-User suchen
        * **accountId** accountId des abgefragten Benutzers
        * **username:
        ### Rückgabewerte
        * 
        """
        return self._processResponse(self._callApi("user/search", locals()), catchCodes=[404])

    def usersGetByName(self, displayName: str = None):
        """
        Nach Jira-User anhand des displayNamens suchen
        * **displayName:
        ### Rückgabewerte
        * 
        """
        users = self.userSearch(query=displayName)
        return list(filter(lambda u: u.displayName == displayName, users))

    def userGroups(self, accountId: str):
        """
        Benutzergruppen zu einem Jira-User ausgeben
        * **accountId** accountId des abgefragten Benutzers
        ### Rückgabewerte
        * 
        """
        return self._processResponse(self._callApi("user/groups", locals()))

    def groupCreate(self, name: str, withUsersAdd: List[str] = None):
        """
        Neue Benutzergruppe erzeugen
        ### Rückgabewerte
        * **name** Name der neuen Gruppe
        * **description** Beschreibung der neuen Gruppe
        * **withUsersAdd** Liste der anzufügenden Benutzer (accountId)
        """
        data = locals()
        del data["withUsersAdd"]
        group = self._processResponse(self._callApi("group", method="POST", data=data), 201)
        if withUsersAdd:
            for accountId in withUsersAdd:
                self.groupUserAdd(accountId, group.groupId)
        return group

    def groupRemove(
        self,
        groupId: str = None,
        groupname: str = None,
        swapGroupId: str = None,
        swapGroup: str = None,
    ):
        """
        Benutzergruppe löschen
        * **groupId** ID der Gruppe
        * **groupname** Name der Gruppe [deprecated]
        * **swapGroupId** ID der Gruppe, zu der die bestehenden Berechtigungen/Beschränkungen übertragen werden sollen
        * **swapGroup** Name der Gruppe, zu der die bestehenden Berechtigungen/Beschränkungen übertragen werden sollen [deprecated]
        """
        if groupId == None and groupname == None:
            raise ValueError("groupId oder groupname sollen gesetzt sein")
        params = locals()

        def notFound(r):
            if r.status_code == 400:
                print("FEHLER: ", r.content)
                raise objectNotExists("swapGroup")
            else:
                raise objectNotExists("group")

        try:
            return self._processResponse(
                self._callApi("group", self._params(params), "DELETE"),
                noresponse=True,
                catchCodes=[404, 400],
                catchClosure=notFound,
            )
        except objectNotExists:
            return False

    def groupSearch(
        self,
        query: str = None,
        excludeId: List[str] = None,
        exclude: List[str] = None,
        caseInsensitive: bool = False,
        maxResults: int = None,
    ):
        """
        Nach Benutzergruppen suchen
        ### Rückgabewerte
        * **query** Zeichenfolge, die im Gruppennamen vorhanden sein muss
        * **excludeId** Liste der Gruppen-IDs, die zu ignorieren sind
        * **exclude** Liste der Gruppen-Namen die zu ignorieren sind [deprecated]
        * **caseInsensitive** Query beachtet keine Groß-/Kleinschreibung
        * **maxResults** Limit der Ergebnisse
        """
        params = locals()
        return self._processResponse(self._callApi("groups/picker", params))

    def groupMember(
        self,
        groupId: str = None,
        groupname: str = None,
        includeInactiveUsers: bool = False,
        maxResults: int = None,
    ):
        """
        Mitglieder einer Benutzergruppe ausgeben [Generator]
        ### Rückgabewerte
        * **groupId** ID der Gruppe
        * **groupname** Name der Gruppe [deprecated]
        * **includeInactiveUsers** Inaktive Benutzer mit aufzählen
        * **maxResults** Limit für Benutzer-Ergebnis-Liste
        ### Rückgabewerte
        *  Iterable[Array der Benutzer] oder None, falls Gruppe nicht existiert
        """
        if groupId == None and groupname == None:
            raise ValueError("groupId oder groupname sollen gesetzt sein")

        def notFound(r):
            raise objectNotExists("group")

        try:
            yield from self._processResponsePaginated("group/member", locals(), catchCodes=[404], catchClosure=notFound)
        except objectNotExists:
            yield None

    def groupUserAdd(self, accountId: str, groupId: str = None, groupname: str = None):
        """
        Benutzer einer Gruppe hinzufügen
        ### Rückgabewerte
        * **accountId** Account-ID des Benutzers, der hinzugefügt werden soll
        * **groupId** ID der Gruppe
        * **groupname** Name der Gruppe [deprecated]
        ### Rückgabewerte
        *  Datensatz der Gruppe (mit aktueller Benutzerliste)
        """
        if groupId == None and groupname == None:
            raise ValueError("groupId oder groupname sollen gesetzt sein")
        params = locals()
        data = {"accountId": params["accountId"]}
        del params["accountId"]

        def notFound(r):
            raise objectNotExists("group")

        try:
            return self._processResponse(
                self._callApi("group/user", self._params(params), "POST", data),
                201,
                catchCodes=[400],
                catchClosure=notFound,
            )
        except objectNotExists:
            return False

    def groupUserDel(self, accountId: str, groupId: str = None, groupname: str = None):
        """
        Benutzer aus einer Gruppe entfernen
        ### Rückgabewerte
        * **accountId** Account-ID des Benutzers, der hinzugefügt werden soll
        * **groupId** ID der Gruppe
        * **groupname** Name der Gruppe [deprecated]
        """
        if groupId == None and groupname == None:
            raise ValueError("groupId oder groupname sollen gesetzt sein")
        params = locals()

        def notFound(r):
            raise objectNotExists("group")

        try:
            return self._processResponse(
                self._callApi("group/user", self._params(params), "DELETE"),
                noresponse=True,
                catchCodes=[404],
                catchClosure=notFound,
            )
        except objectNotExists:
            return False

    def groupUsersSet(
        self,
        setAccountIds: List[str],
        oldAccountIds: List[str] = None,
        groupId: str = None,
        groupname: str = None,
        includeInactiveUsers: bool = False,
    ):
        """
        Benutzer einer Gruppe setzen
        ### Rückgabewerte
        * **setAccountIds** Account-IDs der Benutzer, die in der Gruppe verbleiben/hinzugefügt werden wollen
        * **oldAccountIds** Account-IDs der Benutzer, die aus der Gruppe entfernt werden sollen; wenn nichts angegeben, werden alle aktuellen Nutzer entfernt
        * **groupId** ID der Gruppe
        * **groupname** Name der Gruppe [deprecated]
        * **includeInactiveUsers** Inaktive Benutzer sollen beibehalten werden
        """
        if groupId == None and groupname == None:
            raise ValueError("groupId oder groupname sollen gesetzt sein")
        if oldAccountIds == None:
            oldAccountIds = [m.accountId for m in list(self.groupMember(groupId, groupname, includeInactiveUsers))]
        # neue hinzufügen
        for accountId in setAccountIds:
            if accountId not in oldAccountIds:
                self.groupUserAdd(accountId, groupId, groupname)
        # alte entfernen
        for accountId in oldAccountIds:
            if accountId not in setAccountIds:
                self.groupUserDel(accountId, groupId, groupname)

    def groupUsersAdd(
        self,
        setAccountIds: List[str],
        groupId: str = None,
        groupname: str = None,
        includeInactiveUsers: bool = False,
    ):
        """
        Gruppe um bestimmte Benutzer ergänzen
        ### Rückgabewerte
        * **setAccountIds** Account-IDs der Benutzer, die zur Gruppe hinzugefügt werden wollen
        * **groupId** ID der Gruppe
        * **groupname** Name der Gruppe [deprecated]
        * **includeInactiveUsers** Inaktive Benutzer mit aufzählen
        """
        self.groupUsersSet(setAccountIds, [], groupId, groupname, includeInactiveUsers)

    def filterMy(self, expand: str = None, includeFavourites: bool = False):
        """
        Eigene Jira-Filter ausgeben
        ### Rückgabewerte
        * 
        """
        return self._processResponse(self._callApi("filter/my", locals()))

    def filterSearch(
        self,
        filterName: str = None,
        accountId: str = None,
        groupname: str = None,
        groupId: str = None,
        projectId: str = None,
        orderBy: str = None,
        expand: str = None,
        overrideSharePermissions: bool = False,
        startAt: int = None,
        maxResults: int = None,
    ) -> Iterable:
        """
        Jira-Filter suchen
        https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-filters/#api-rest-api-3-filter-search-get
        ### Rückgabewerte
        *  Iterable[Array an Filtern]
        """
        yield from self._processResponsePaginated("filter/search", locals())

    def filterGet(self, id):
        """
        Jira-Filter abrufen
        * **id** ID des Filters
        ### Rückgabewerte
        * 
        """

        def errors(response: requests.Response):
            if (
                response.status_code == 404
                and response.content
                and ut.loads(response.content.decode("utf-8")).errorMessages[0]
                in ("Der ausgewählte Filter steht Ihnen nicht zur Verfügung. Er wurde eventuell gelöscht oder seine Berechtigungen wurden geändert.")
            ):
                return None

        try:
            return self._processResponse(self._callApi(f"filter/{id}"), catchCodes=[400, 404], catchClosure=errors)
        except objectNotExists:
            return None

    def filterUpdate(
        self,
        id: int,
        name: str,
        jql: str = None,
        description: str = None,
        favourite: bool = None,
        sharePermissions: List[dict] = None,
        editPermissions: List[dict] = None,
        expand: str = None,
        overrideSharePermissions: bool = False,
    ):
        """
        Jira-Filter schreiben
        * **id** ID des Filters
        * **name** Name des Filters
        * **jql** jql des Filters
        * **description** Beschreibung des Filters
        * **favourite** Filter für aktuellen Benutzer als Favoriten markieren
        * **sharePermissions** Betrachtungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        * **editPermissions** Bearbeitungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        """
        data = locals()
        del data["id"], data["expand"], data["overrideSharePermissions"]
        data = self.permissionsWritable(data)
        return self._processResponse(
            self._callApi(
                f"filter/{id}",
                {
                    "expand": expand,
                    "overrideSharePermissions": overrideSharePermissions,
                },
                "PUT",
                data,
            )
        )

    def filterOwner(self, id, accountId):
        """
        Eigentümer eines Jira-Filters setzen
        * **id** ID des Filters
        * **accountId** accountId des neuen Eigentümers
        """

        def errors(response: requests.Response):
            if response.status_code == 400 and response.content and ut.loads(response.content.decode("utf-8")).errorMessages[0] == "The user already owns a filter with the same name.":
                return -1

        return self._processResponse(
            self._callApi(f"filter/{id}/owner", method="PUT", data={"accountId": accountId}),
            204,
            catchCodes=[400],
            catchClosure=errors,
        )

    def agileBoards(self, name: str = None, maxResults: int = None):
        """
        Sämtliche Software/Agile-Boards auflisten
        * **name** Teilstring des Board-Namens
        """
        yield from self._processResponsePaginated("board", locals(), apiVersion="agile")

    def agileBoardConfig(self, id: int):
        """
        Board-Konfiguration auslesen
        * **id** ID des Boards
        """
        return self._callSeveralProcessResponse(
            f"rapidviewconfig/editmodel.json?rapidViewId={id}&cardLayoutConfig=false",
            apiVersion="greenhopper",
        )

    def agileBoardAdminSet(self, id: int, userKeys: List[str], groupKeys: List[str]):
        """
        Board-Konfiguration setzen
        * **id** ID des Boards
        * **userKeys** Liste der Benutzer (accountId)
        * **groupKeys** Liste der Gruppen (accountId)
        """
        data = {"id": id, "boardAdmins": {"userKeys": userKeys, "groupKeys": groupKeys}}
        return self._callSeveralProcessResponse(
            f"rapidviewconfig/boardadmins",
            method="PUT",
            data=data,
            apiVersion="greenhopper",
        )

    def dashboard(self, filter: str = None, startAt: int = None, maxResults: int = None) -> Iterable:
        """
        Sämtliche Jira-Dashboards abrufen [Generator]
        ### Rückgabewerte
        *  Iterable[Array von Dashboard-Objekten]
        """
        return self._processResponsePaginated("dashboard", locals(), "dashboards")

    def dashboardSearch(
        self,
        dashboardName: str = None,
        accountId: str = None,
        groupname: str = None,
        groupId: str = None,
        projectId: str = None,
        orderBy: str = None,
        status: str = "active",
        expand: str = None,
        startAt: int = None,
        maxResults: int = None,
    ):
        """
        Nach Jira-Dashboards suchen
        ### Rückgabewerte
        * 
        """
        return self._processResponsePaginated("dashboard/search", locals())

    def dashboardGet(self, id):
        """
        Jira-Dashboard abrufen
        * **id** ID des Filters
        ### Rückgabewerte
        * 
        """
        try:
            return self._processResponse(self._callApi(f"dashboard/{id}"), catchCodes=[404])
        except objectNotExists:
            return None

    def dashboardUpdate(
        self,
        id: int,
        name: str,
        description: str = None,
        sharePermissions: List[dict] = None,
        editPermissions: List[dict] = None,
    ):
        """
        Jira-Dashboard schreiben
        * **id** ID des Dashboards
        * **name** Name des Dashboards
        * **description** Beschreibung des Dashboards
        * **sharePermissions** Betrachtungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        * **editPermissions** Bearbeitungs-Freigaben, Liste von Objekten {'type':"user/group/project/projectRole/global/loggedin/project-unknown",'user':{'accountId':""},'group':{'groupId/name':""},'project':{'id':"",'email':"",'favourite':True/False},'role':{'name':"",'translatedName':"",'currentUserRole':True/False}}
        """
        data = locals()
        del data["id"], data["self"]
        if not sharePermissions or not editPermissions:
            dashboard = self.permissionsWritable(self.dashboardGet(id))
            data["sharePermissions"] = dashboard["sharePermissions"] if not sharePermissions else data["sharePermissions"]
            data["editPermissions"] = dashboard["editPermissions"] if not editPermissions else data["editPermissions"]
        return self._processResponse(self._callApi(f"dashboard/{id}", method="PUT", data=data))

    def permissionsWritable(self, entryOrPermission: List[dict] | dict | SimpleNamespace | List[SimpleNamespace]):
        """
        Dünnnt die editPermissions bzw. sharePermissions-Arrays auf das zum Schreiben Notwendige aus.
        ### Parameter
        * entryOrPermission: List[dict] | dict
            * Eintrag (z.B. JiraFilter oder Dashboard) als [dict] mit `editPermissions` bzw. `sharePermissions` als Eigenschaften, bzw. direkt diese Eigenschaften
        ### Rückgabe
        * Modifizierter Input
        """
        entryOrPermission = ut.normalize(entryOrPermission)
        try:
            newperms = []
            permtypes = (
                {"permission": entryOrPermission}
                if (type(entryOrPermission) == list)
                else {"editPermissions": entryOrPermission["editPermissions"], "sharePermissions": entryOrPermission["sharePermissions"]}
            )
            for typ in permtypes:
                newperms = []
                if permtypes[typ] == None:
                    permtypes[typ] = []
                for perm in permtypes[typ]:
                    unbekannt = False
                    if perm["type"] == "user":
                        perm["user"] = {"accountId": perm["user"]["accountId"]}
                    elif perm["type"] == "group":
                        if "groupId" in perm["group"]:
                            perm["group"] = {"groupId": perm["group"]["groupId"]}
                        else:
                            perm["group"] = {"name": perm["group"]["name"]}
                    elif perm["type"] == "project":
                        perm["project"] = {"id": perm["project"]["id"]}
                    elif perm["type"] == "projectRole":
                        perm["role"] = {"name": perm["role"]["name"]}
                    else:
                        print("   >>> Unbekannt: ", perm)
                        unbekannt = True
                    if "id" in perm:
                        del perm["id"]
                    if not unbekannt:
                        newperms.append(perm)
                if type(entryOrPermission) != list:
                    entryOrPermission[typ] = newperms
            return newperms if type(entryOrPermission) == list else entryOrPermission
        except Exception as e:
            print("FEHLER mit Permissions:")
            print(e, ut.pretty(entryOrPermission))

    def _proceedAdminList(self, tr):
        tds = list(tr.find_all("td"))
        name = "".join(list(tds[0].div.span.stripped_strings))
        ownerName = "".join(list(tds[1].span.stripped_strings))
        if ownerName in ("None", "Keine"):
            ownerName = []
        perms = {}
        permissions = {}
        permissions["sharable"] = tds[2]
        permissions["editable"] = tds[3]
        for perm in permissions:
            perms[perm] = []
            if permissions[perm].find("li", {"class": "private"}):
                continue
            for ul in permissions[perm].find_all("ul"):
                if "id" in ul.attrs and "list_summary" in ul.attrs["id"]:
                    continue
                for li in ul.find_all("li", {"class": "public"}):
                    if li.attrs["title"] in (
                        "Freigegeben für angemeldete Benutzer",
                        "Shared with logged-in users",
                    ):
                        perms[perm].append({"type": "loggedin"})
                        continue
                    type = str(li.contents[1].string)
                    inhalt = str(li.contents[2]).strip(":").strip()
                    inhalt = inhalt.replace("(ANZEIGEN)", "").replace("(VIEW)", "").replace("(BEARBEITEN)", "").replace("(EDIT)", "").strip()
                    if type in ("Benutzer", "User"):
                        perms[perm].append({"type": "user", "user": {"displayName": inhalt}})
                    elif type in ("Projekt", "Project"):
                        perms[perm].append({"type": "project", "project": {"name": inhalt}})
                    elif type in ("Gruppe", "Group"):
                        perms[perm].append({"type": "group", "group": {"name": inhalt}})
                    else:
                        perms[perm].append({"type": "unbekannt", "inhalt": inhalt})
        yield ut.simplifize(
            {
                "id": tr.attrs["id"][3:],
                "name": name,
                "owner": {"displayName": ownerName},
                "sharePermissions": perms["editable"],
                "editPermissions": perms["editable"],
                "isWritable": False,
            }
        )

    def filterAdminlist(
        self,
        limit: int | None = None,
        includeTrash: bool = False,
        skipRestable: bool = False,
        pagingOffset: int = 0,
    ):
        def startsWithMf(id):
            return id.startswith("mf_")

        offsets = {"browse": pagingOffset}
        if includeTrash:
            offsets["trash_browse"] = pagingOffset
        count = 0
        while True:
            soup, resp = self._callGui(
                "secure/admin/filters/ViewSharedFilters.jspa?pagingOffset="
                + str(offsets["browse"])
                + "&trashPagingOffset="
                + str(offsets["trash_browse"] if "trash_browse" in offsets else 0)
                + f"&showTrashList={includeTrash}"
            )
            for typ in offsets:
                if limit != None and count >= limit:
                    break
                if offsets[typ] == -1:
                    continue
                if soup.find("table", id=f"mf_{typ}"):
                    for tr in soup.find("table", id=f"mf_{typ}").find("tbody").find_all("tr", id=startsWithMf):
                        if limit != None and count >= limit:
                            break
                        filt = self.filterGet(tr.attrs["id"][3:])
                        if filt != None:
                            if skipRestable:
                                continue
                            yield filt
                            count += 1
                        else:
                            yield from self._proceedAdminList(tr)
                            count += 1
                else:
                    offsets[typ] = -1
                    continue
                offsets[typ] += 1
            if offsets["browse"] == -1 and ("trash_browse" not in offsets or offsets["trash_browse"] == -1):
                break
            if limit != None and count >= limit:
                break

    def dashboardAdminlist(
        self,
        limit: int | None = None,
        includeTrash: bool = False,
        skipRestable: bool = False,
    ):
        def startsWithPp(id):
            return id.startswith("pp_")

        offsets = {"browse": 0}
        if includeTrash:
            offsets["trash_browse"] = 0
        count = 0
        while True:
            soup, resp = self._callGui(
                "secure/admin/dashboards/ViewSharedDashboards.jspa?pagingOffset="
                + str(offsets["browse"])
                + "&trashPagingOffset="
                + str(offsets["trash_browse"] if "trash_browse" in offsets else 0)
                + f"&showTrashList={includeTrash}"
            )
            for typ in offsets:
                if limit != None and count >= limit:
                    break
                if offsets[typ] == -1:
                    continue
                try:
                    for tr in soup.find("table", id=f"pp_{typ}").find("tbody").find_all("tr", id=startsWithPp):
                        if limit != None and count >= limit:
                            break
                        dashb = self.dashboardGet(tr.attrs["id"][3:])
                        if dashb != None:
                            if skipRestable:
                                continue
                            yield dashb
                            count += 1
                        else:
                            yield from self._proceedAdminList(tr)
                            count += 1
                except:
                    offsets[typ] = -1
                    continue
                offsets[typ] += 1
            if offsets["browse"] == -1 and ("trash_browse" not in offsets or offsets["trash_browse"] == -1):
                break
            if limit != None and count >= limit:
                break

    def dashboardOwner(self, dashboardId: int, accountId: str):
        """
        Jira-Dashboard Owner ändern
        * **dashboardId** ID des zu übereignenden Dashboards
        * **accountId** accountId des neuen Eigentümers
        """
        soup, resp = self._callGui("secure/admin/dashboards/ViewSharedDashboards.jspa")
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
            cookies=resp.cookies,
            auth=self.auth,
        )
        return self._processResponse(response, noresponse=True)


class ConfluenceApi(AtlassianCloud):
    def __init__(self, username: str, apikey: str, base_url: str = None) -> None:
        super().__init__(username, apikey, base_url)
        self._api_urls = {2: "wiki/api/v2/", 1: "wiki/rest/api/"}
        self._api_version = 2

    def _processResponsePaginated(self, call: str, params: dict = None, resultsKey: str = "results", apiVersion: int | str | None = None) -> Iterable | None:
        """Rückgabe eines seitenweise operierenden API-Aufrufs (GET) verarbeiten

        ### Parameter
        * **call `str`** URL des Aufrufs (nach "wiki/api/v2/" bzw. "wiki/rest/api/")
        * **params `dict` (Default None)** Aufruf-Parameter
        * **resultsKey `str` (Default "results")** Wie heißt die Eigenschaft des Rückgabe-JSONs, in dem die Ergebnisse erwartet werden?
        * **apiVersion `int | str | None` (Default None)** API-Version

        ### Fehler-Behandlungen:
            Exception: Cursor wurde nicht gefunden

        ### Rückgabewerte
        * `None`, wenn keine Ergebnisse vorhanden
        * `Iterable`, sofern Ergebnisse vorliegen
        """
        limit = None if "limit" not in params else params["limit"]
        if limit == None:
            params["limit"] = 25
        elif limit > 250:
            params["limit"] = 250
        results = self._processResponse(self._callApi(call, params, apiVersion=apiVersion))
        totalCount = 0
        if results == None:
            return None
        else:
            count = len(getattr(results, resultsKey))  # Standard-Seitengröße
            totalCount += count
            for result in getattr(results, resultsKey):
                yield result
        while results != None and hasattr(results._links, "next") and (limit == None or totalCount < limit):
            # params['Cursor'] = results._links.next.split('&cursor=')[1] + ';rel="next"'
            try:
                parsed_url = urlparse(results._links.next)
                params["cursor"] = parse_qs(parsed_url.query)["cursor"][0]
            except:
                print("Cursor nicht gefunden! " + results._links.next)
                raise Exception("Cursor nicht gefunden! ")
            if limit != None and totalCount + count > limit:
                params["limit"] = count - (totalCount + count - limit)
            results = self._processResponse(self._callApi(call, params, apiVersion=apiVersion))
            if results == None:
                return None
            else:
                for result in getattr(results, resultsKey):
                    yield result

    def search(
        self,
        cql: str,
        cqlcontext: dict | None = None,
        limit: int | None = 25,
        start: int = 0,
        includeArchivedSpaces: bool = False,
        excludeCurrentSpaces: bool = False,
        excerpt: str  = "highlight",
        sitePermissionTypeFilter: str = "none",
        ) -> Iterable | None:
        """CQL-Suche ausführen

        ### Parameter
        * **cql `str`** CQL-Suchausdruck (https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)
        * **cqlcontext `dict | None` (Default None)** Bereich, Content und Content-Status für die Suche.
            * `spaceKey` [optional] Bereichs-Schlüssel, in dem gesucht werden soll
            * `contentId` ID des Contents, in dem gesucht werden soll (muss im Bereich `spaceKey` liegen)
            * `contentStatuses` [optional] Content-Status, nach denen gesucht werden soll
        * **limit `int | None` (Default 25)** Nach wie vielen Ergebnissen soll die Suche abgebrochen werden?
        * **start `int | None` (Default 0)** Such-Offset
        * **includeArchivedSpaces `bool` (Default False)** Archivierte Bereiche auch durchsuchen
        * **excludeCurrentSpaces `bool` (Default False)** Aktuelle (d.h. nicht-archivierte) Bereiche von der Suche ausschließen
        * **excerpt `str` (Default "highlight")** Auszugs-Strategie im Suchergebnis, eins von `highlight`, `indexed`, `none`, `highlight_unescaped`, `indexed_unescaped`
        * **sitePermissionTypeFilter `str` (Default "none")**

        ### Rückgabewerte
        * `None`, wenn keine Ergebnisse vorhanden
        * `Iterable`, sofern Ergebnisse vorliegen
        """
        yield from self._processResponsePaginated("search", locals(), apiVersion=1)

    def pages(
        self,
        id: List[int] = None,
        title: str = None,
        status: str = None,
        body_format: str = "storage",
        limit: str = None,
        sort: str = None,
        serialize_ids_as_strings: bool = False,
    ):
        """
        Alle Seiten ausgeben
        ### Rückgabewerte
        * **body_format: storage oder atlas_doc_format
        ### Rückgabewerte
        * 
        """
        yield from self._processResponsePaginated("pages", self._params(locals()))

    def labelsPages(
        self,
        label: str | int = None,
        body_format: str = "storage",
        space_id: List[int] = None,
        limit: str = None,
        sort: str = None,
        serialize_ids_as_strings: bool = False,
    ) -> Iterable:
        """
        Alle Seiten zu einem Label ausgeben
        ### Rückgabewerte
        * **label** ID des Labels als int oder Name des Labels als str
        * **body_format: storage oder atlas_doc_format
        * **space_id: IDs der Bereiche, auf die die Ergebnisse ggf. begrenzt werden sollen
        ### Rückgabewerte
        *  Iterable[Array an Page-Objekten]
        """
        params = locals()
        del params["label"]
        if type(label) is str:
            labelinf = self.labelInformation(label, "page")
            label = labelinf.label.id
        if space_id and isinstance(space_id, list):
            space_id = ",".join([str(n) for n in space_id])
        yield from self._processResponsePaginated(f"labels/{label}/pages", self._params(params))

    def pagesChildren(
        self,
        id: int,
        sort: str = None,
        limit: str = None,
        serialize_ids_as_strings: bool = False,
    ):
        """
        Alle Unterseiten ausgeben
        ### Rückgabewerte
        * **id** ID der Seite, deren Unterseiten ausgegeben werden sollen
        * **sort** Feldname, nach dem die Ausgabe sortiert werden soll
        ### Rückgabewerte
        * 
        """
        params = locals()
        del params["id"]
        yield from self._processResponsePaginated(f"pages/{id}/children", self._params(params))

    def pagesSort(self, parentId: int, order: str | Callable = "ASC", recursive: bool = False):
        """
        Seiten eines Zweigs sortieren
        ### Rückgabewerte
        * **parentId** ID der Seite, deren Unterseiten sortiert werden sollen
        * **order** Reihenfolge: ASC= alph. aufsteigend, DESC= alph. absteigend; oder eine Compare-Funktion (mit return 1,0 oder -1), die als Elemente jeweils Dicts mit folgenden Keys bekommt: id, title, status, spaceId, childPosition
        """
        pages = list(self.pagesChildren(parentId, sort="title"))
        if callable(order):
            pages = sorted(pages, key=cmp_to_key(order))
        for index in range(len(pages)):
            if index < len(pages) - 1:  # letzte Seite nicht verschieben
                yield (
                    pages[index + 1].id,
                    pages[index + 1].title,
                    "before" if not callable(order) and order == "DESC" else "after",
                    pages[index].id,
                    pages[index].title,
                    ut.pretty(
                        self.contentMove(
                            pages[index + 1].id,
                            ("before" if not callable(order) and order == "DESC" else "after"),
                            pages[index].id,
                        ),
                        False,
                        None,
                    ),
                )
            if recursive:
                yield from self.pagesSort(pages[index].id, order, recursive)

    def pageCreate(
        self,
        spaceId: int,
        title: str = None,
        parentId: int = None,
        body: dict | str = None,
        body_format: str = "storage",
        status: str = "current",
        private: bool = False,
        embedded: bool = False,
        serialize_ids_as_strings: bool = False,
    ):
        """
        Seite erzeugen
        ### Rückgabewerte
        * **body** je nach body_format: storage -> HTML/XML; atlas_doc_format -> Inhalt von body.atlas_doc_format.value als dict
        * **body_format: storage oder atlas_doc_format
        ### Rückgabewerte
        * 
        """
        data = locals()
        params = {}
        for param in ("private", "embedded", "serialize_ids_as_strings"):
            params[param] = data[param]
            del data[param]

        if body_format == "storage":
            data["body"] = {"storage": {"representation": "storage", "value": data["body"]}}
        else:
            data["body"] = {
                "atlas_doc_format": {
                    "representation": "atlas_doc_format",
                    "value": ut.dumps(data["body"]),
                }
            }
        return self._processResponse(self._callApi(f"pages", self._params(params), "POST", data))

    def pageUpdate(
        self,
        id: int,
        title: str = None,
        parentId: int = None,
        body: dict | str = None,
        body_format: str = "storage",
        status: str = "current",
        version: dict | None = None,
        serialize_ids_as_strings: bool = False,
    ):
        """
        Seite aktualisieren
        ### Rückgabewerte
        * **id:
        * **body** je nach body_format: storage -> HTML/XML; atlas_doc_format -> Inhalt von body.atlas_doc_format.value als dict
        * **body_format: storage oder atlas_doc_format
        * **version** Version als {'number':<int>,'message':'<string>','minorEdit':<bool>}
        ### Rückgabewerte
        * 
        """
        data = locals()
        params = {}
        param = "serialize_ids_as_strings"
        params[param] = data[param]
        del data[param]

        if body_format == "storage":
            data["body"] = {"storage": {"representation": "storage", "value": data["body"]}}
        elif body_format == "atlas_doc_format":
            data["body"] = {
                "atlas_doc_format": {
                    "representation": "atlas_doc_format",
                    "value": ut.dumps(data["body"]),
                }
            }
        del data["body_format"]
        if version == None:
            page = self.page(id)
            data["version"] = {"number": (int(page.version.number) + 1), "message": ""}
        return self._processResponse(self._callApi(f"pages/{id}", self._params(params), "PUT", data))

    def page(
        self,
        id: int,
        version: int = None,
        get_draft: bool = False,
        status: str = None,
        body_format: str = "storage",
        serialize_ids_as_strings: bool = False,
    ):
        """
        Einzelne Seite samt Informationen abrufen
        ### Parameter
        * **id `int`** ID der Seite
        * **version `int` (Default None)** Nummer der dedizierten Version. Wenn nicht angegeben, aktuelle
        * **get_draft `bool` (Default False)** Entwurf abrufen
        * **status `str`(Default None)** Mögliche Status im Ergebnis; mehrere Werte per Komma verketten. Status: `current`, `trashed`, `deleted`, `draft`
        * **body_format `str`** storage oder atlas_doc_format
        ### Rückgabewerte
        * 
        """
        params = locals()
        del params["id"]
        return self._processResponse(self._callApi(f"pages/{id}", self._params(params)), catchCodes=[404], catchClosure=self._notFoundStatus)
    
    def blogpost(
        self,
        id: int,
        version: int = None,
        get_draft: bool = False,
        status: str = None,
        body_format: str = "storage",
        serialize_ids_as_strings: bool = False,
    ):
        """
        Einzelnen Blogpost samt Informationen abrufen
        ### Parameter
        * **id `int`** ID der Seite
        * **version `int` (Default None)** Nummer der dedizierten Version. Wenn nicht angegeben, aktuelle
        * **get_draft `bool` (Default False)** Entwurf abrufen
        * **status `str`(Default None)** Mögliche Status im Ergebnis; mehrere Werte per Komma verketten. Status: `current`, `trashed`, `deleted`, `historical`, `draft`
        * **body_format `str`** storage oder atlas_doc_format
        ### Rückgabewerte
        * 
        """
        params = locals()
        del params["id"]
        return self._processResponse(self._callApi(f"blogposts/{id}", self._params(params)), catchCodes=[404], catchClosure=self._notFoundStatus)
    
    def space(
        self,
        id: int,
    ):
        """
        Einzelnen Bereich samt Informationen abrufen
        ### Parameter
        * **id `int`** ID der Seite
        ### Rückgabewerte
        * 
        """
        params = locals()
        del params["id"]
        return self._processResponse(self._callApi(f"spaces/{id}", self._params(params)), catchCodes=[404], catchClosure=self._notFoundStatus)

    def pageLabels(
        self,
        id: int,
        prefix: str = None,
    ):
        """
        Labels einer einzelnen Seite abrufen
        ### Rückgabewerte
        * **id** Page-ID
        * **prefix** my, team, global, system als mögliche Werte
        ### Rückgabewerte
        *  Aktuelle Label-Definition der Seite
        """
        params = locals()
        del params["id"]
        return self._processResponse(self._callApi(f"pages/{id}/labels", self._params(params)))

    def contentAddLabels(self, id: int, labels: List[dict] | dict):
        """
        Stichworte eines Contents / einer Seite aktualisieren
        * **id** ID des betroffenen Contents
        * **labels** Labels, die angefügt werden sollen
        ### Rückgabewerte
        *  Aktuelle Label-Definition der Seite
        """
        return self._processResponse(
            self._callApi(
                f"content/{id}/label",
                method="POST",
                data=labels,
                apiVersion=1,
            )
        )

    def contentMove(self, pageId: int, position: str, targetId: int):
        """
        Seite verschieben
        ### Rückgabewerte
        * **pageId** ID der zu verschiebenden Seite
        * **position** Richtung der Verschiebung: before - vor die Ziel-Seite; after - hinter die Ziel-Seite; append - unter die Ziel-Seite (anfügen)
        * **targetId** ID der Ziel-Seite
        ### Rückgabewerte
        *  pageId
        """
        return self._processResponse(
            self._callApi(
                f"content/{pageId}/move/{position}/{targetId}",
                method="PUT",
                apiVersion=1,
            )
        )

    def contentDescendants(self, id: int, expand: List[str] = None):
        """
        Seite verschieben
        ### Rückgabewerte
        * **id:
        * **expand** attachment, comments, page
        ### Rückgabewerte
        *  pageId
        """
        params = locals()
        del params["id"]
        return self._processResponse(self._callApi(f"content/{id}/descendant", self._params(params), apiVersion=1))

    def labelInformation(self, name: str, type: str = None, start: int = None, limit: int = None):
        """
        Informationen zum Label abrufen
        ### Rückgabewerte
        * **name** Name des Labels
        * **type** page, blogpost, attachment, page_template
        * **start** Offset für Ausgabe verknüpfter Inhalte
        :para limit: Limit für Ausgabe verknüpfter Inhalte
        """
        return self._processResponse(self._callApi("label", self._params(locals()), apiVersion=1))


class AssetsApi(AtlassianCloud):
    def __init__(self, username: str, apikey: str, base_url: str = None) -> None:
        super().__init__(username, apikey, base_url)
        self._api_version = 1

    def setBase(self, baseurl: str) -> None:
        super().setBase(baseurl)
        response = requests.request(
            "GET",
            f"{self.base_url}/rest/servicedeskapi/assets/workspace",
            auth=self.auth,
            headers={"Accept": "application/json"},
        )
        if response.status_code == 200:
            workspace = ut.loads(response.text)
            self.workspaceId = workspace.values[0].workspaceId
            self.base_url2 = self.base_url
            self.base_url = f"https://api.atlassian.com/jsm/assets/workspace/{self.workspaceId}/"
            self._api_urls = {
                1: "v1/",
                "assets": f"gateway/api/jsm/assets/workspace/{self.workspaceId}/v1/",
                "insight": f"gateway/api/jsm/insight/workspace/{self.workspaceId}/v1/",
            }
        else:
            raise objectNotExists("WorkspaceID nicht gefunden!")

    def _callDirect(
        self,
        call: str,
        params: dict = None,
        method="GET",
        data: dict = None,
        apiVersion: int | str = None,
    ):
        return self._callApi(call, params, method, data, apiVersion, self.base_url2)

    def objectschemaList(self, startAt: int = None) -> Iterable:
        """
        Listet alle Objektschemata auf
        ### Rückgabewerte
        *  Iterable[Array von Objektschema-Objekten]
        """
        yield from self._processResponsePaginated("objectschema/list", locals())

    def objectschemaGet(self, id: str):
        """
        Einzelnes Objektschema aufrufen
        ### Rückgabewerte
        * **id** Objektschema-ID
        ### Rückgabewerte
        *  Objektschema-Objekt
        """
        return self._processResponse(self._callApi(f"objectschema/{id}"))

    def objectschemaObjecttypes(self, id: str, excludeAbstract: bool = False):
        """
        Objekttypen eines Objektschemas auflisten
        ### Rückgabewerte
        * **id** Objektschema-ID
        * **excludeAbstract** Abstrakte Objekttypen ausschließen aus der Auflistung
        ### Rückgabewerte
        *  Objekt {'entries':[je Objekttyp ein Objekt]}
        """
        return self._processResponse(self._callApi(f"objectschema/{id}/objecttypes", locals()))

    def objectschemaAttributes(
        self,
        id: str,
        query: str = "",
        onlyValueEditable: bool = False,
        extended: bool = False,
    ):
        """
        Sämtliche Attribute eines Objektschemas auflisten
        * **id** Objektschema-ID
        * **query** Suchausdruck zum Filtern der Ergebnisse anhand des Attribut-Namens
        * **onlyValueEditable** Nur Werte ausgeben, die editierbar sind
        * **extended** In jedem Attribut-Eintrag die Objekttyp-Struktur einbinden, zu der er gehört
        ### Rückgabewerte
        *  List[Attribut-Objekte]
        """
        return self._processResponse(self._callApi(f"objectschema/{id}/attributes", locals()))

    def objecttypeAttributes(
        self,
        id: str,
        query: str = "",
        onlyValueEditable: bool = False,
        includeChildren: bool = False,
        excludeParentAttributes: bool = False,
        includeValuesExist: bool = False,
        orderByName: bool = False,
        orderByRequired: bool = False,
    ):
        """
        Attribute eines Objekttypen auflisten
        ### Rückgabewerte
        * **id** Objekttyp-ID
        * **query** Suchausdruck zum Filtern der Ergebnisse anhand des Attribut-Namens
        * **onlyValueEditable** Nur Werte ausgeben, die editierbar sind
        ### Rückgabewerte
        *  List[Attribut-Objekte]
        """
        return self._processResponse(self._callApi(f"objecttype/{id}/attributes"))

    def configRoleActors(self, roleId: str):
        """
        Berechtigte einer Konfigurations-Rolle (Object Schema Users/Developers/Managers) abrufen
        * **id** ID der Konfigurations-Rolle
        ### Rückgabewerte
        *  {'id':id, 'actors':[Objekt je Berechtigten], ...}
        """
        return self._processResponse(self._callDirect(f"config/role/{roleId}", apiVersion="insight"))

    def configRoleObjectschema(self, id: str):
        """
        Konfigurations-Rollen eines Objektschemas abrufen
        * **id** Objectschema-ID
        ### Rückgabewerte
        *  {'Object Schema Users/Developers/Managers':{'id':id, 'actors':[Objekt je Berechtigten], ...}}
        """
        roles = ut.normalize(self._processResponse(self._callDirect(f"config/role/objectschema/{id}", apiVersion="assets")))
        for role in roles:
            roles[role] = self.configRoleActors(roles[role].split("/")[-1])
        return roles

    def configRoleObjecttype(self, id: str):
        """
        Konfigurations-Rollen eines Objekttypen abrufen
        * **id** Objekttyp-ID
        ### Rückgabewerte
        *  {'Object Schema Users/Developers/Managers':{'id':id, 'actors':[Objekt je Berechtigten], ...}}
        """
        roles = ut.normalize(self._processResponse(self._callDirect(f"config/role/objecttype/{id}", apiVersion="assets")))
        for role in roles:
            roles[role] = self.configRoleActors(roles[role].split("/")[-1])
        return roles

    def configRoleUpdate(
        self,
        roleId: str = None,
        userActors: List[str] = [],
        groupActors: List[str] = [],
    ):
        """
        Konfigurations-Rollen aktualisieren
        * **roleId** Konfigurations-Rollen-ID
        * **userActors** Liste der accountIds
        * **groupActors** Liste der Gruppen-Namen
        ### Rückgabewerte
        *  {'id':id, 'actors':[Objekt je Berechtigten], ...}
        """
        data = {
            "id": roleId,
            "categorisedActors": {
                "atlassian-group-role-actor": groupActors,
                "atlassian-user-role-actor": userActors,
            },
        }
        return self._processResponse(self._callDirect(f"config/role/{roleId}", method="PUT", data=data, apiVersion="assets"))

    def objectAql(self, qlQuery: str, includeAttributes: bool = True, maxResults: int = 25) -> Iterable:
        """
        Objekte anhand einer AQL abrufen
        ### Rückgabewerte
        * **qlQuery** AQL
        * **includeAttributes** Objekt-Attribute mit anzeigen
        * **maxResults** Wie viele Ergebnisse sollen angezeigt werden
        ### Rückgabewerte
        *  Iterable[Objekte]
        """
        yield from self._processResponsePaginated("object/aql", locals(), data={"qlQuery": qlQuery}, method="POST")
