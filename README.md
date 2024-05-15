### Inhaltsverzeichnis

* [Spickzettel](#spickzettel)

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
pip install jonazarov -U
```
