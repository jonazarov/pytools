import json, codecs, sys, time
from os.path import dirname
from types import SimpleNamespace
from prompt_toolkit.shortcuts import input_dialog, yes_no_dialog
from prompt_toolkit.styles import Style


class NamespaceEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (list, tuple)):
            return super(NamespaceEncoder, self).iterencode(o)
        return o.__dict__

class Unbuffered:
    def __init__(self, logfile, stream):
        self.logfile = logfile
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        self.logfile.write(data)  # Write the data of stdout here to a text file as well

    def flush(self):

        # this flush method is needed for python 3 compatibility.
        # this handles the flush command by doing nothing.
        # you might want to specify some extra behavior here.
        pass


def confunpack(confdef: dict, config: dict, pt_style: Style = None) -> dict:
    """Befüllt ein Config-Dict anhand einer conf-Definition aus einer Config-File sowie aus Dialog-Eingaben
    ### Parameter
    * **condef `dict`** Config-Definition
    * **config `dict`** Dict aus Config-File
    * **pt_style `style` (Default None)** Formatierung der Dialoge
    ### Rückgabewerte
    * Neues Config-Dict
    """
    for entry in confdef:
        # Wenn Endpunkt erreicht, Daten per Dialog anfordern
        if type(confdef[entry]) is str:
            centry = entry if not str(entry).endswith('?') else entry[:-1]
            if not centry in config:
                if str(entry).endswith('?'):
                    config[centry] = yes_no_dialog(title="Fehlende Konfigurations-Informationen ergänzen", yes_text="Ja", no_text="Nein", text=confdef[entry], style=pt_style).run()
                else:
                    config[centry] = ""
                    while config[centry] == "":
                        config[centry] = input_dialog(title="Fehlende Konfigurations-Informationen ergänzen", cancel_text="Abbruch", text=confdef[entry], style=pt_style).run()
                    if config[centry] == None:
                        sys.exit()
        # Wenn Unterpunkt
        else:
            if not entry in config or not (type(config[entry]) is dict):
                config[entry] = {}
            config[entry] = confunpack(confdef[entry], config[entry])
    return config


class Utils:
    pt_style = Style.from_dict(
        {
            "dialog": "bg:#94D5E4",
            "dialog frame.label": "bg:#e30613 #FFFFFF",
            "dialog.body": "bg:#009FE3 #173861",
            "dialog shadow": "bg:#3C9CB2",
            "dialog button": "bg:#e30613 #FFFFFF",
            "dialog button.focused": "bg:#173861 #e30613",
            "dialog checkbox-checked": "bg:#E30613",
            "dialog checkbox-selected": "bg:#ff8288",
        }
    )

    def pretty(data: dict | list | str, sort_keys: bool = True, indent: int | None = 4) -> json:
        """Gibt beliebige Dicts/Lists/Tupel etc. formatiert aus
        ### Parameter
        * **data `dict|list|str`** zu formatierende Daten (List, Dictionary, Tupel, String etc.)
        * **sort_keys `bool` (Default True)** Nach Schlüssel alphabetisch sortieren
        * **indent `int` (Default 4)** Einzug neuer Zeilen. Wenn None, kein Zeilenumbruch
        ### Rückgabewerte
        * `json` JSON-String
        """
        try:
            data2 = data.decode("utf-8")
            return data2
        except (UnicodeDecodeError, AttributeError):
            pass
        return json.dumps(data, sort_keys=sort_keys, indent=indent, ensure_ascii=False, separators=(",", ": "), cls=NamespaceEncoder)

    def loads(data: json) -> SimpleNamespace:
        """Lädt ein JSON-String in SimpleNamespace

        ### Parameter
        * **data `json`** Zu verarbeitendes JSON-String

        ### Rückgabewerte
        * `SimpleNamespace`
        """
        return json.loads(data, object_hook=lambda x: SimpleNamespace(**x))

    def load(file) -> SimpleNamespace:
        """Lädt eine JSON-Datei in SimpleNamespace

        ### Parameter
        * **file** File-Object

        ### Rückgabewerte
        * `SimpleNamespace`
        """
        return json.load(file, object_hook=lambda x: SimpleNamespace(**x))

    def normalize(data: dict | list | str | int | SimpleNamespace) -> dict | list | str:
        """Liefert beliebige Daten (inkl. SimpleNamespace-Objekte) in normalen Python-Größen aus

        ### Parameter
        * **data `dict | list | str | int | SimpleNamespace`**

        ### Rückgabewerte
        * `dict | list | str`
        """
        return json.loads(json.dumps(data, cls=NamespaceEncoder))

    def simplifize(data: dict | list | str | int) -> SimpleNamespace:
        """Verwandelt normale Python-Größen in SimpleNamespace

        ### Parameter
        * **data `dict | list | str | int`**

        ### Rückgabewerte
        * `SimpleNamespace`
        """
        return Utils.loads(Utils.dumps(data))

    def dumps(data: dict | list | str | int | SimpleNamespace) -> json:
        """Gibt beliebige Daten (inkl. SimpleNamespace-Objekte) als JSON-String aus

        ### Parameter
        * **data `dict | list | str | int | SimpleNamespace`**

        ### Rückgabewerte
        * `json` JSON-String
        """
        return json.dumps(Utils.normalize(data))

    def log(filename: str | None = None, manual: bool = False):
        """Logging vorbereiten

        ### Parameter
        * **filename `str | None` (Default None)** In welcher Datei soll der Log geschrieben werden? Wenn nichts angegeben, wird im Verzeichnis der aufrufenden Datei eine Datei erzeugt, zusammengesetzt aus dem Dateinamen der aufrufenden Datei und `.%Y-%m-%d.log`
        * **manual `bool` (Default False)** Manueller Log-Modus. Wenn True, gibt die Funktion das File-Objekt zurück, in welches mit `Utils.logline()` geschrieben werden kann. Ansonsten wird automatisch jedes Print in die Datei geschrieben

        ### Rückgabewerte
        * File-Objekt, falls `manual == True`
        """
        if filename == None:
            import inspect
            filename = inspect.stack()[len(inspect.stack())-1][1]
        now = time.localtime()
        logfilename = filename + time.strftime(".%Y-%m-%d.log", now)
        logfile = codecs.open(logfilename, "a", encoding="utf-8")
        logfile.write("NewLogEntry " + time.strftime("%Y-%m-%d %H:%M:%S", now) + "\n")
        sys.stdout = Unbuffered(logfile, sys.stdout)
        return logfile

    def logline(logfile, *values: str, sep: str | None = " ", end: str | None = "\n"):
        """Einzelne Zeile in Logdatei manuell schreiben

        ### Parameter
        * **logfile** File-Objekt der Logdatei
        * ***values `str`** Zu schreibende Strings
        * **sep `str | None` (Default " ")** Trenner zwischen den zu schreibenden Strings
        * **end `str | None` (Default "\n")** Trenner am Ende einer zu schreibenden Zeile
        """
        if sep == None:
            sep = " "
        if end == None:
            end = "\n"
        if logfile != None:
            print(*values, sep=sep, end=end)
            logfile.write(sep.join(values) + end)
            logfile.flush()

    def _conffile(configfile: str | None = None) -> str:
        """Namen der Konfigurationsdatei bestimmen (wenn nichts angegeben, wird eine config.json im Unterverzeichnis der aufrufenden Datei angenommen)

        ### Parameter
        * **conffile `str | None` (Default None)** Dateiname der Konfigurationsdatei

        ### Rückgabewerte
        * `str`
        """
        if configfile == None:
            p = None
            if getattr(sys, "frozen", False):
                p = dirname(sys.executable)
            else:
                import inspect
                p = dirname(inspect.stack()[len(inspect.stack())-1][1])
            configfile = f"{p}\\config.json"
            return configfile
        return configfile

    def getconfig(confdef: dict, conffile: str | None = None) -> SimpleNamespace:
        """Konfigurationsdatei auslesen, anhand der Konfigiurationsdefinition befüllen und als SimpleNamespace ausgeben

        ### Parameter
        * **confdef `dict`** Konfigurations-Definition, Key entsprechend der Eigenschaft in der Konfigurationsdatei, Wert entsprechend der Beschreibung für Anforderungs-Dialog; Verschachtelung möglich
        * **conffile `str | None` (Default None)** Dateiname der Konfigurationsdatei

        ### Rückgabewerte
        * `SimpleNamespace` Fertig ausgelesene Konfiguration
        """
        conffile = Utils._conffile(conffile)
        config = {}
        with open(conffile, "a+", encoding="utf-8") as file:
            file.seek(0)
            try:
                config = json.load(file)
            except:
                pass
        return Utils.simplifize(confunpack(confdef, config, Utils.pt_style))
    
    def setconfig(config: SimpleNamespace | dict, conffile: str | None = None):
        """Konfigurationsdatei (über)schreiben

        ### Parameter
        * **config `SimpleNamespace | dict`** Zu schreibende Konfiguration
        * **conffile `str | None` (Default None)** Dateiname der Konfigurationsdatei
        """
        conffile = Utils._conffile(conffile)
        with open(conffile, "w", encoding="utf-8") as file:
            json.dump(Utils.normalize(config), file, indent=3, ensure_ascii=False)


def lprint(logfile, *values: str, sep: str | None = " ", end: str | None = "\n"):
    """print-Ersatz für das manuelle Schreiben des Logs

    ### Parameter
    * **logfile** File-Objekt der Logdatei
    * ***values `str`** Zu schreibende Strings
    * **sep `str | None` (Default " ")** Trenner zwischen den zu schreibenden Strings
    * **end `str | None` (Default "\n")** Trenner am Ende einer zu schreibenden Zeile
    """
    Utils.logline(logfile, *values, sep=sep, end=end)
