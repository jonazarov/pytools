import json, pathlib, inspect
from types import SimpleNamespace

class NamespaceEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (list, tuple)):
            return super(NamespaceEncoder,self).iterencode(o)
        return o.__dict__ 
    
import codecs, sys, time
class Unbuffered:
    def __init__(self, logfile, stream):
        self.logfile = logfile
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        self.logfile.write(data)    # Write the data of stdout here to a text file as well

    def flush(self):

        # this flush method is needed for python 3 compatibility.
        # this handles the flush command by doing nothing.
        # you might want to specify some extra behavior here.
        pass    

def confunpack(confdef: dict, config: dict) -> dict:
    '''
    Befüllt ein Config-Dict anhand einer conf-Definition aus einer Config-File sowie aus Input-Eingaben
    :param condef: Config-Definition
    :param config: Dict aus Config-File
    :return: Neues Config-Dict
    '''
    for entry in confdef:
        if type(confdef[entry]) is str:
            if not entry in config:
                config[entry] = input(confdef[entry])
        else:
            if not entry in config:
                config[entry] = {}
            config[entry] = confunpack(confdef[entry], config[entry])
    return config

class Utils:
    def pretty(data: dict | list | str, sort_keys:bool=True, indent:bool|None = 4) -> json:
        '''
        Gibt beliebige Dicts/Lists/Tupel etc. formatiert aus
        '''
        try:
            data2 = data.decode('utf-8')
            return data2
        except (UnicodeDecodeError, AttributeError):
            pass
        return json.dumps(data, sort_keys=sort_keys, indent=indent, ensure_ascii=False, separators=(",", ": "), cls=NamespaceEncoder)
    
    def loads(data: json) -> SimpleNamespace:
        '''
        Lädt ein JSON-String in SimpleNamespace
        '''
        return json.loads(data, object_hook= lambda x: SimpleNamespace(**x))
    
    def load(file) -> SimpleNamespace:
        '''
        Lädt eine JSON-Datei in SimpleNamespace
        '''
        return json.load(file, object_hook= lambda x: SimpleNamespace(**x))

    def normalize(data: dict | list | str) -> dict | list | str:
        '''
        Verwandelt ein SimpleNamespace-Objekt in normale Python-Größen
        '''
        return json.loads(json.dumps(data, cls=NamespaceEncoder))
    
    def simplifize(data: dict | list | str | int) -> SimpleNamespace:
        '''
        Verwandelt normale Python-Größen in SimpleNamespace
        '''
        return Utils.loads(Utils.dumps(data))
    
    def dumps(data: dict | list | str | int) -> json:
        return json.dumps(Utils.normalize(data))
    
    def log(current_filename: str|None = None):
        if configfile == None:
            configfile = pathlib.Path(inspect.stack()[1][1]).resolve()
        now = time.localtime()
        logfilename = current_filename + time.strftime(".%Y-%m-%d.log", now)
        logfile = codecs.open(logfilename, 'a', encoding='utf-8')
        logfile.write("NewLogEntry "+time.strftime("%Y-%m-%d %H:%M:%S", now) + "\n")
        sys.stdout = Unbuffered(logfile, sys.stdout)

    def getconfig(confdef: dict, conffile: str) -> SimpleNamespace:
        config = {}
        with open(conffile, "r", encoding="utf-8") as file:
            try:
                config = json.load(file)
            except:
                pass
        return Utils.simplifize(confunpack(confdef, config))