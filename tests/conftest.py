import pytest
import requests_mock


@pytest.fixture(autouse=True)
def requests_mocker():
    # This is autouse to protect tests against accidentally doing real
    # requests without it being noticed.
    with requests_mock.Mocker() as m:
        yield m
