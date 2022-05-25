import sys
import textwrap

from mirror_tool.cmd import entrypoint
from mirror_tool.gitlab import GitlabSession


def test_basic_update_gitlab(tmpdir, monkeypatch, caplog, run_git):
    """mirror-tool can do basic updates with gitlab integration enabled."""

    # This test only goes as far as verifying that GitlabSession is invoked with
    # appropriate arguments after the local update. Correctness of GitlabSession
    # needs to be verified elsewhere.

    repo1 = tmpdir.join("repo1")
    repo2 = tmpdir.join("repo2")
    reposuper = tmpdir.join("super")

    # Prepare all three git repos with some content.
    run_git("init", "-b", "main", repo1)
    run_git("init", "-b", "main", repo2)
    run_git("init", "-b", "main", reposuper)

    repo1.join("file1").write("1")
    run_git("add", "file1", cwd=str(repo1))
    run_git("commit", "-m", "commit in repo1", cwd=str(repo1))

    repo2.join("file2").write("2")
    run_git("add", "file2", cwd=str(repo2))
    run_git("commit", "-m", "commit in repo2", cwd=str(repo2))

    reposuper.join(".mirror-tool.yaml").write(
        textwrap.dedent(
            f"""
            mirror:
            - url: ../repo1
              ref: refs/heads/main
              dir: mirror1
            - url: ../repo2
              ref: refs/heads/main
              dir: mirror2
            git_config:
              user.name: test
              user.email: tester@example.com
            gitlab_merge:
              enabled: true
            """
        )
    )
    run_git("add", ".mirror-tool.yaml", cwd=str(reposuper))
    run_git("commit", "-m", "add config", cwd=str(reposuper))

    # running from top level of superproject.
    monkeypatch.chdir(str(reposuper))

    # Set some of the env vars which would normally be set by gitlab CI.
    monkeypatch.setenv("CI_API_V4_URL", "https://gitlab.example.com/api")
    monkeypatch.setenv("CI_PROJECT_ID", "123")
    monkeypatch.setenv("CI_PROJECT_URL", "https://gitlab.example.com/best/project")
    monkeypatch.setenv("GITLAB_MIRROR_TOKEN", "abc123")

    monkeypatch.setattr(sys, "argv", ["", "update"])

    updates = []

    def fake_ensure_merge_request_exists(self):
        updates.extend(self.updates)

    monkeypatch.setattr(
        GitlabSession, "ensure_merge_request_exists", fake_ensure_merge_request_exists
    )

    # It should run OK
    entrypoint()

    # ensure_merge_request_exists should have been invoked with appropriate updates
    assert len(updates) == 2
    assert updates[0].mirror.dir == "mirror1"
    assert updates[1].mirror.dir == "mirror2"
    assert len(updates[0].commits) == 1
    assert len(updates[1].commits) == 1
