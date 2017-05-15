from __future__ import absolute_import, division, print_function

import os
import sys
import subprocess

import time

try:
    from urllib.request import urlopen
    from urllib.error import HTTPError, URLError
except ImportError:  # Python 2.x
    from urllib2 import urlopen, HTTPError, URLError

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "tests")))
import m3u8server

TEST_SERVER_STDOUT = "tests/server.stdout"
TEST_SERVER_URL = "http://{host}:{port}/path/to/redirect_me".format(**m3u8server.SERVER_ADDRESS)


@pytest.fixture(scope="session")
def m3u8_server(request):
    out_and_err_f = open(TEST_SERVER_STDOUT, 'w')
    try:
        server_process = subprocess.Popen(["python", os.path.join("tests", "m3u8server.py")],
                                          stdout=out_and_err_f, stderr=out_and_err_f)
        try:
            start_time = time.time()
            while (time.time() - start_time) < 3.0:
                try:
                    u = urlopen(TEST_SERVER_URL)
                except HTTPError:
                    break
                except URLError as ue:
                    if ue.args[0].errno == 61:  # Connection refused because server is not ready yet
                        time.sleep(0.2)
                        continue
                    raise
                else:
                    u.close()
                    break
            yield None
        finally:
            server_process.kill()
    finally:
        out_and_err_f.close()
