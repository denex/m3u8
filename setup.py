"""
Package maker
"""
from os.path import dirname, abspath, join, exists
from setuptools import setup

LONG_DESCRIPTION_TEXT = None
if exists("README.rst"):
    with open("README.rst") as f:
        LONG_DESCRIPTION_TEXT = f.read()

INSTALL_REQS = tuple([req for req in open(abspath(join(dirname(__file__), 'requirements.txt')))])

setup(
    name="m3u8",
    author='Globo.com',
    author_email='videos3@corp.globo.com',
    version="0.3.2",
    license='MIT',
    zip_safe=False,
    include_package_data=True,
    install_requires=INSTALL_REQS,
    packages=["m3u8"],
    url="https://github.com/globocom/m3u8",
    description="Python m3u8 parser",
    long_description=LONG_DESCRIPTION_TEXT
)
