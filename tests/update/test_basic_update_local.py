import os
import sys
import textwrap

import pytest

from mirror_tool.cmd import entrypoint


# If no target system is enabled, then update and update-local are just the
# same thing, so test with both
@pytest.mark.parametrize("subcommand", ["update", "update-local"])
def test_basic_update_local(tmpdir, monkeypatch, caplog, run_git, subcommand):
    """mirror-tool can do basic local updates."""

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
            """
        )
    )
    run_git("add", ".mirror-tool.yaml", cwd=str(reposuper))
    run_git("commit", "-m", "add config", cwd=str(reposuper))

    # Simulate the case where this dir already exists under superproject
    # but with some junk.
    reposuper.mkdir("mirror2").join("junk").write("")

    # running from top level of superproject.
    monkeypatch.chdir(str(reposuper))

    monkeypatch.setattr(sys, "argv", ["", subcommand, "--allow-empty"])

    # It should run OK
    entrypoint()

    # Should tell us it's done
    assert "Mirror(s) locally updated." in caplog.text

    # Files from the mirrors should be present in the superproject
    assert os.path.exists(str(reposuper.join("mirror1/file1")))
    assert os.path.exists(str(reposuper.join("mirror2/file2")))

    # And anything not in the mirrors no longer exists
    assert os.path.exists(str(reposuper.join("mirror2/junk")))
