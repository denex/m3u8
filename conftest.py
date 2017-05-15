from __future__ import absolute_import, division, print_function

import os
import subprocess

import pytest

TEST_SERVER_STDOUT = "tests/server.stdout"


@pytest.fixture(scope="session")
def m3u8_server(request):
    out_and_err_f = open(TEST_SERVER_STDOUT, 'w')
    server_process = subprocess.Popen(["python", os.path.join("tests", "m3u8server.py")],
                                      stdout=out_and_err_f, stderr=out_and_err_f)
    yield None
    out_and_err_f.close()
    server_process.kill()
