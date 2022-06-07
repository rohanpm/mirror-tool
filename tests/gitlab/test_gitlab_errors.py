import pytest
import requests_mock

from mirror_tool.conf import GitlabMerge
from mirror_tool.gitlab import GitlabException, GitlabUpdateSession


def test_missing_settings():
    """GitlabSession raises a sane error if required settings are missing."""

    merge = GitlabMerge(api_v4_url=None)

    # It should raise
    with pytest.raises(GitlabException) as excinfo:
        GitlabUpdateSession(merge, run_cmd=lambda: (), updates=[])

    # It should tell me why
    assert "'api_v4_url' is not set" in str(excinfo.value)


def test_push_fails(monkeypatch):
    """GitlabSession raises if git push command fails."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    merge = GitlabMerge(
        api_v4_url="https://example.com/",
        project_id=123,
        push_url="https://example.com/push",
    )

    def run_cmd_error(*args, **kwargs):
        raise RuntimeError("simulating failure to run command...")

    session = GitlabUpdateSession(merge, run_cmd=run_cmd_error, updates=[])

    # In this test just simulate that the revision is not already present while
    # avoiding having to run any git commands
    monkeypatch.setattr(session, "revision_in_remote_branch", lambda *_: False)

    # It should raise when I ask it to create an MR
    with pytest.raises(GitlabException) as excinfo:
        session.ensure_merge_request_exists()

    # It should tell me why
    assert "Could not push" in str(excinfo.value)


def test_request_fails(monkeypatch, requests_mocker: requests_mock.Mocker, caplog):
    """GitlabSession raises if requests to gitlab fail."""

    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123-not-a-real-token")

    merge = GitlabMerge(
        api_v4_url="https://example.com/api",
        project_id=123,
        push_url="https://example.com/push",
    )

    def run_cmd_ok(*args, **kwargs):
        pass

    requests_mocker.post(
        "https://example.com/api/projects/123/merge_requests",
        status_code=500,
        json={"some": "response"},
    )

    session = GitlabUpdateSession(merge, run_cmd=run_cmd_ok, updates=[])

    # In this test just simulate that the revision is not already present while
    # avoiding having to run any git commands
    monkeypatch.setattr(session, "revision_in_remote_branch", lambda *_: False)

    # It should raise when I ask it to create an MR
    with pytest.raises(GitlabException) as excinfo:
        session.ensure_merge_request_exists()

    # It should tell me why
    assert "Failed to create merge request" in str(excinfo.value)

    # And logs should have mentioned the response
    assert "Unexpected response from GitLab: 500" in caplog.text
    assert "{'some': 'response'}" in caplog.text
