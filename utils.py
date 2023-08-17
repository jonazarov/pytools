import json
from types import SimpleNamespace

class NamespaceEncoder(json.JSONEncoder):
    def default(self, o):
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
        try:
            data2 = data.decode('utf-8')
            return data2
        except (UnicodeDecodeError, AttributeError):
            pass
        return json.dumps(data, sort_keys=sort_keys, indent=indent, ensure_ascii=False, separators=(",", ": "), cls=NamespaceEncoder)
    
    def loads(data: json) -> SimpleNamespace:
        return json.loads(data, object_hook= lambda x: SimpleNamespace(**x))
    
    def load(file) -> SimpleNamespace:
        return json.load(file, object_hook= lambda x: SimpleNamespace(**x))

    def normalize(data: dict | list | str) -> dict | list | str:
        return json.loads(json.dumps(data, cls=NamespaceEncoder)) if type(data) is SimpleNamespace or type(data) is list else data
    
    def simplifize(data: dict | list | str | int) -> SimpleNamespace:
        return Utils.loads(Utils.dumps(data))
    
    def dumps(data: dict | list | str | int) -> json:
        return json.dumps(Utils.normalize(data))
    
    def log(current_filename: str):
        now = time.localtime()
        logfilename = current_filename + time.strftime(".%Y-%m-%d.log", now)
        print(logfilename)
        logfile = codecs.open(logfilename, 'a', encoding='utf-8')
        logfile.write("NewLogEntry "+time.strftime("%Y-%m-%d %H:%M:%S", now) + "\n")
        sys.stdout = Unbuffered(logfile, sys.stdout)

    def getconfig(confdef: dict, conffile: str) -> SimpleNamespace:
        config = {}
        with open(conffile, "r") as file:
            try:
                config = json.load(file)
            except:
                pass
        return Utils.simplifize(confunpack(confdef, config))