### Inhaltsverzeichnis

* [Spickzettel](#spickzettel)
    * [fly.io](#flyio)
    * [Filament](#filament)
        * [Resourcen anlegen](#resourcen-anlegen)
        * [Einstellungen in Resourcen vornehmen](#einstellungen-in-resourcen-vornehmen)
        * [Relation Manager anlegen](#relation-manager-anlegen)
        * [Diverse Befehle](#diverse-befehle)
    * [Laravel](#laravel)
        * [Models generieren](#models-generieren)
        * [Eloquent Queries](#eloquent-queries)
        * [Eloquent Relationen](#eloquent-relationen)
        * [Artisan Befehle](#artisan-befehle)
    * [Git](#git)
        * [Git aufsetzen](#git-aufsetzen)
        * [Repo verbinden](#repo-verbinden)
* [Dokumentation](#dokumentation)

# Spickzettel
https://betterscientificsoftware.github.io/python-for-hpc/tutorials/python-pypi-packaging

## Package Update
* Code aktualisieren
* Version in `__init__.py` aktualisieren
* Version in `setup.py` aktualisieren
```shell
# Vorbereiten der Dateien und Upload in https://test.pypi.org/project/jonazarov/
deploy.bat
# Wenn alles funktioniert, Upload ins produktive pypi
upload.bat
# Installation der produktiven Packages
pip install jonazarov
```
