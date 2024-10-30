from jonazarov.utils import Utils as ut
import codecs, re, os

class ReportSection:
    def __init__(self, name:str, cols:tuple, header:str | None = None, options:dict = {}, noentries_message:str | None = None, path:str | None = None, filename: str | None = None):
        """Weitere Report-Sektion erzeugen

        ### Parameter
        * **name `str`** interner Name zur Identifikation
        * **cols `tuple`** Liste der Spalten, die in einem Eintrag verwendet werden
        * **header `str` (optional)** Beschriftung/Überschrift der Sektion
        * **options `dict` (optional)** Optionen
            * `header` Tupel mit Spalten, die als Überschrift formatiert werden sollen
            * `link` Tupel mit Spalten, die einen Link enthalten; als Wert für die Zelle wird dann ein `tuple` erwartet (URL und optional Beschriftung)
            * `entries` Name der Spalte, deren Einträge gezählt werden sollen
        * **noentries_message `str` (optional)** Meldung, die angezeigt werden soll, wenn keine Einträge vorhanden

        ### Rückgabe
        * `self`
        """
        self.name = ut.valid_html_id(name)
        self.header = header or name
        self.cols = cols
        self.options = {'header': (), 'link': (), 'entries': ''}
        self.options.update(options)
        self.noentries_message = noentries_message or ('0 ' + self.header + 's')
        self.entries = 0

        filename = filename or ut.caller().removesuffix('.py')
        path = (path or ut.callerRoot()).removesuffix('/').removesuffix('\\')
        self.filename = path + '/' + filename
        self.sectionfile = codecs.open(self.filename + '.sections.'+self.name+'.html', "w", encoding="utf-8")
        self.sectionfile.write(f"""
            <h3 id="{self.name}">{self.header}</h3>
            <table class="table table-striped">
                <thead>
                    <tr>
                        """)
        for col in self.cols:
            self.sectionfile.write(f'<th scope="col">{col}</th>')
        self.sectionfile.write("""
                    </tr>
                </thead>
                <tbody>""")
        self.sectionfile.flush()
    
    def entry(self, entry:dict):
        entries = 1
        self.sectionfile.write("""
                    <tr>""")
        for col in self.cols:
            if not col in entry:
                self.sectionfile.write('<td></td>')
                continue

            if col in self.options['entries']:
                entries = len(entry[col]) if type(entry[col]) == list else (1 if entry[col] else 0)

            if col in self.options['header']:
                self.sectionfile.write("""
                        <th scope="row">""")
            else:
                self.sectionfile.write("""
                        <td>""")

            if type(entry[col]) == list:
                self.sectionfile.write(f"""
                            <ul class="list-group">
                                {"\n                                ".join(['<li class="list-group-item font-monospace bg-white" style="--bs-bg-opacity: .5;">'+ point +'</li>' for point in entry[col]])}
                            </ul>""")
            elif col in self.options['link']:
                if type(entry[col]) == tuple and len(entry[col]) > 1:
                    self.sectionfile.write(f"""
                            <a href="{entry[col][0]}" target="_blank">{entry[col][1]}</a>
                    """)
                else:
                        self.sectionfile.write(f"""
                            <a href="{entry[col]}" target="_blank">{entry[col]}</a>
                    """)
            else:
                self.sectionfile.write(entry[col])
            
            if col in self.options['header']:
                self.sectionfile.write("""
                        </th>""")
            else:
                self.sectionfile.write("""
                        </td>""")
        self.sectionfile.write("""
                    </tr>""")
        self.sectionfile.flush()
        self.entries += entries

    def finish(self):
        if self.entries < 1:
            self.sectionfile.write(f"""
                    <tr>
                        <th scope="row" colspan="3" class="text-center">{self.noentries_message}</th>
                    </tr>""")
        else:
            self.tocfile = codecs.open(self.filename + '.toc.html', "a", encoding="utf-8")
            self.tocfile.write(f"""
                <li id="toc-{self.name}"><a href="#{self.name}">{self.entries} {self.header}</a></li>""")
            self.tocfile.close()
        self.sectionfile.write("""
                </tbody>
            </table>""")
        self.sectionfile.close()

class Report:
    """HTML-Reports mit Tabellen erzeugen
    """
    def __init__(self, title:str | None = None, header:str | None = None, language:str = 'en', filename:str | None = None, path:str | None = None):
        """Report-Instanz erzeugen

        ### Parameter
        * **title `str` (optional)** HTML-Titel des Reports (alternativ wird header oder filename verwendet)
        * **header `str` (optional)** Überschrift des Reports (alternativ wird title oder filename verwendet)
        * **language `str` (Default: en)** Sprachcodierung für HTML
        * **filename `str` (optional)** Dateiname des Reports (alternativ wird title oder header oder Dateiname der Python-Datei verwendet)
        * **path `str` (optional)** Speicher-Verzeichnis des Reports (alternativ wird Verzeichnis der ausgeführten Datei verwendet)
        """
        self.filename = (filename or title or header or ut.caller()).removesuffix('.html')
        self.title = re.sub('<[^<]+?>', '', (title or header or self.filename))
        self.header = header or title or self.filename
        self.path = (path or ut.callerRoot()).removesuffix('/').removesuffix('\\')
        self.head = codecs.open(self.path + '/' + self.filename + '.head.html', "w", encoding="utf-8")
        self.foot = codecs.open(self.path + '/' + self.filename + '.foot.html', "w", encoding="utf-8")
        self.head.write(f"""<!doctype html>
<html lang="{language}">
    <head>
        <meta charset="UTF-8" />
        <title>{self.title}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">
        <style>"""
            + """
            .stickyButton {
                position: fixed;
                bottom: 10px;
                right: 20px;
                z-index: 1000;
            }

            @media (min-width: 1380px) {
                .stickyButton {
                    right: calc((100% - 1300px) / 2 - 50px);
                }
            }"""
            + f"""
        </style>
    </head>
    <body>
    <div class="container pb-1" id="top"></div>
        <div class="container mt-5">
            <h2>{self.header}</h2>""")
        self.head.close()
        
        self.foot.write("""
        </div>
    </body>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.11.8/dist/umd/popper.min.js" crossorigin="anonymous"></script>
    <script>
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
        const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
    </script>
</html>""")
        self.foot.close()
        self.sections = {}

        self.tocfile = codecs.open(self.path + '/' + self.filename + '.toc.html', "w+", encoding="utf-8")
        self.tocfile.write("""
            <ul class="py-3">""")
        self.tocfile.close()


    def section(self, name:str, cols:tuple, header:str | None = None, options:dict = {}, noentries_message:str | None = None) -> ReportSection:
        """Weitere Report-Sektion erzeugen

        ### Parameter
        * **name `str`** interner Name zur Identifikation
        * **cols `tuple`** Liste der Spalten, die in einem Eintrag verwendet werden
        * **header `str` (optional)** Beschriftung/Überschrift der Sektion
        * **options `dict` (optional)** Optionen
            * `header` Tupel mit Spalten, die als Überschrift formatiert werden sollen
            * `link` Tupel mit Spalten, die einen Link enthalten; als Wert für die Zelle wird dann ein `tuple` erwartet (URL und optional Beschriftung)
            * `entries` Name der Spalte, deren Einträge gezählt werden sollen
        * **noentries_message `str` (optional)** Meldung, die angezeigt werden soll, wenn keine Einträge vorhanden

        ### Rückgabe
        * `ReportSection`
        """
        section = ReportSection(name, cols, header, options, noentries_message, self.path, self.filename)
        self.sections[section.name] = section
        return section

    def finish(self, start:bool=False):
        """Finalisiert den Report

        ### Parameter
        * **start `bool` (Default: False)** Nach Abschluss soll die Datei geöffnet werden im Browser
        """
        self.tocfile = codecs.open(self.tocfile.name, 'a', encoding='utf-8')
        self.tocfile.write("""
            </ul>
            <h3 class="stickyButton"><a href="#top" data-bs-toggle="tooltip" data-bs-title="Zum Seitenanfang"><span class="badge text-bg-primary">&uArr;</span></a></h3>""")
        self.tocfile.close()

        files = [
            self.head.name,
            self.tocfile.name,
            ]

        for name in self.sections:
            self.sections[name].finish()
            files.append(self.sections[name].sectionfile.name)

        files.append(self.foot.name)
        self.filename = self.path + '/' + self.filename + '.html'
        ut.merge_utf8_files(files, self.filename)
        for name in self.sections:
            os.remove(self.sections[name].sectionfile.name)
        for file in (self.head, self.tocfile, self.foot):
            os.remove(file.name)

        if start:
            os.startfile(self.filename)