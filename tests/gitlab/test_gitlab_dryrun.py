import logging

import pytest
import requests_mock

from mirror_tool.conf import GitlabMerge
from mirror_tool.gitlab import GitlabUpdateSession


@pytest.mark.parametrize(
    "mutator",
    [
        (lambda s: s.create_mr()),
        (lambda s: s.update_mr({"iid": 12345})),
        (lambda s: s.ensure_pushed_to("abc123", "dest")),
        (lambda s: s.add_comment({"iid": 112233}, "my fake comment")),
    ],
    ids=["create", "update", "push", "comment"],
)
def test_dryrun_method(
    monkeypatch, requests_mocker: requests_mock.Mocker, caplog, mutator
):
    """GitlabSession in dry-run mode doesn't do any HTTP requests."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
        src="some-src",
        dest="some-dest",
    )

    def run_cmd_raise(*args, **kwargs):
        # Should not try to run any commands.
        raise AssertionError("unexpectedly ran a command: %s" % (args, kwargs))

    caplog.set_level(logging.INFO)
    session = GitlabUpdateSession(
        merge, run_cmd=run_cmd_raise, updates=[], dry_run=True
    )

    # It should run without crashing...
    mutator(session)

    # ...but it didn't actually do anything.
    assert requests_mocker.request_history == []

    # And it should have mentioned dry run.
    assert "DRY RUN" in caplog.text
