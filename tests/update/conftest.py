from subprocess import check_call

import pytest

from mirror_tool.git_config import environ_with_git_config


@pytest.fixture
def run_git():
    env = environ_with_git_config(
        {"user.name": "test", "user.email": "mirror-tool@example.com"}
    )

    def run(*args, **kwargs):
        return check_call(["git"] + [str(a) for a in args], env=env, **kwargs)

    return run
