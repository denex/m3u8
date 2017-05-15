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
# noinspection PyPep8,PyUnresolvedReferences
import m3u8server

TEST_SERVER_STDOUT = "tests/server.stdout"
TEST_SERVER_URL = "http://{host}:{port}/path/to/redirect_me".format(**m3u8server.SERVER_ADDRESS)
TEST_SERVER_STARTUP_TIMEOUT_SEC = 2.0


# noinspection PyUnusedLocal
@pytest.fixture(scope="session")
def m3u8_server(request):
    out_and_err_f = open(TEST_SERVER_STDOUT, 'w')
    try:
        server_process = subprocess.Popen(["python", os.path.join("tests", "m3u8server.py")],
                                          stdout=out_and_err_f, stderr=out_and_err_f)
        try:
            start_time = time.time()
            while (time.time() - start_time) < TEST_SERVER_STARTUP_TIMEOUT_SEC:
                try:
                    u = urlopen(TEST_SERVER_URL, timeout=(TEST_SERVER_STARTUP_TIMEOUT_SEC / 2))
                except HTTPError:
                    break
                except URLError as ue:
                    if ue.args[0].errno == 61:  # Connection refused because server is not ready yet
                        time.sleep(TEST_SERVER_STARTUP_TIMEOUT_SEC / 10)
                        continue
                    raise
                else:
                    u.close()
                    break
            else:
                raise Exception("Test server has not started in %.1f sec" % TEST_SERVER_STARTUP_TIMEOUT_SEC)
            assert server_process.poll() is None, "Test server died"
            yield None
        finally:
            server_process.kill()
    finally:
        out_and_err_f.close()
