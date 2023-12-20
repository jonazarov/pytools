from setuptools import setup

setup(
    name='jonazarov',
    version='0.1.2',    
    description='Verschiedene Python-Tools, vor allem für Atlassian Cloud',
    url='https://github.com/jonazarov/pytools',
    author='Johannes Nazarov',
    author_email='johannes.nazarov+dev@gmail.com',
    license='GNU',
    packages=['jonazarov'],
    install_requires=['requests>=2.31.0',
                      'bs4>=0.0.1'
                      ],

    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License (GPL)',  
        'Natural Language :: German',
        'Operating System :: Microsoft :: Windows :: Windows 11',      
        'Programming Language :: Python',
    ],
)