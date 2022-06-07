import sys
import textwrap

from mirror_tool.cmd import entrypoint
from mirror_tool.gitlab import GitlabPromoteSession


def test_basic_promote_gitlab(tmpdir, monkeypatch):
    """mirror-tool can do a basic gitlab promote operation."""

    tmpdir.join(".mirror-tool.yaml").write(
        textwrap.dedent(
            f"""
            mirror: []
            gitlab_promote:
            - src: mysrc
              dest: mydest
            - src: mysrc2
              dest: mydest2
            """
        )
    )

    monkeypatch.chdir(str(tmpdir))

    monkeypatch.setattr(sys, "argv", ["", "promote"])

    # Set some of the env vars which would normally be set by gitlab CI.
    monkeypatch.setenv("CI_API_V4_URL", "https://gitlab.example.com/api")
    monkeypatch.setenv("CI_PROJECT_ID", "123")
    monkeypatch.setenv("CI_PROJECT_URL", "https://gitlab.example.com/best/project")
    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123")

    calls = []

    def fake_ensure(self):
        calls.append(self.gitlab_promote)

    monkeypatch.setattr(
        GitlabPromoteSession,
        "ensure_promotion_merge_request_exists",
        fake_ensure,
    )

    # It should run OK
    entrypoint()

    # It should have called the expected method
    assert len(calls) == 2

    # With details loaded from settings
    assert calls[0].working_branch == "mirror-tool/promote-mysrc-to-mydest"
    assert calls[1].working_branch == "mirror-tool/promote-mysrc2-to-mydest2"


def test_promote_nothing(tmpdir, monkeypatch, caplog):
    """mirror-tool successfully does nothing if no promotion configured."""

    tmpdir.join(".mirror-tool.yaml").write(
        textwrap.dedent(
            f"""
            mirror: []
            """
        )
    )

    monkeypatch.chdir(str(tmpdir))

    monkeypatch.setattr(sys, "argv", ["", "promote"])

    # It should run OK
    entrypoint()

    # It should tell us there was nothing to do
    assert "No remote targets have any promotion rules" in caplog.text
