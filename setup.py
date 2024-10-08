from setuptools import setup

setup(
    name='jonazarov',
    version='0.1.12',    
    description='Verschiedene Python-Tools, u.a. für: Atlassian-Cloud, HRworks-API',
    url='https://github.com/jonazarov/pytools',
    author='Johannes Nazarov',
    author_email='johannes.nazarov+dev@gmail.com',
    license='GNU',
    packages=['jonazarov'],
    install_requires=['requests>=2.31.0',
                      'bs4>=0.0.1',
                      'lxml>=5.2.2',
                      'prompt_toolkit>=3.0.43'
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