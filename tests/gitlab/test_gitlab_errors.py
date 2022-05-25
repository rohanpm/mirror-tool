import pytest

from mirror_tool.conf import GitlabMerge
from mirror_tool.gitlab import GitlabException, GitlabSession


def test_missing_settings():
    """GitlabSession raises a sane error if required settings are missing."""

    merge = GitlabMerge(api_v4_url=None)

    # It should raise
    with pytest.raises(GitlabException) as excinfo:
        GitlabSession(merge, run_cmd=lambda: (), updates=[])

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

    session = GitlabSession(merge, run_cmd=run_cmd_error, updates=[])

    # It should raise when I ask it to create an MR
    with pytest.raises(GitlabException) as excinfo:
        session.ensure_merge_request_exists()

    # It should tell me why
    assert "Could not push" in str(excinfo.value)
