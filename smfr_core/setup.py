from setuptools import setup, find_packages

setup(
    name='smfrcore',
    version='1.0',
    packages=find_packages(),
    description='SMFR Core modules (models, utilities)',
    author='Domenico Nappo',
    author_email='domenico.nappo@ext.ec.europa.eu',
    install_requires=['sqlalchemy_utils', 'flask', 'flask-sqlalchemy', 'flask-cqlalchemy'],
)