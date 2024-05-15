rd dist /S /Q
rd build /S /Q
python setup.py sdist
twine upload --repository-url https://test.pypi.org/legacy/ dist/*