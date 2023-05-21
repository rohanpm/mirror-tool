import os
import sys
import textwrap

from mirror_tool.cmd import entrypoint


def test_update_with_skip(tmpdir, monkeypatch, caplog, run_git):
    """--skip option will skip processing of listed mirror(s)."""

    repo1 = tmpdir.join("repo1")
    repo2 = tmpdir.join("repo2")
    repo3 = tmpdir.join("repo3")
    repo4 = tmpdir.join("repo4")
    reposuper = tmpdir.join("super")

    # Prepare all git repos with some content.
    run_git("init", "-b", "main", repo1)
    run_git("init", "-b", "main", repo2)
    run_git("init", "-b", "main", repo3)
    run_git("init", "-b", "main", repo4)
    run_git("init", "-b", "main", reposuper)

    repo1.join("file1").write("1")
    run_git("add", "file1", cwd=str(repo1))
    run_git("commit", "-m", "commit in repo1", cwd=str(repo1))

    repo2.join("file2").write("2")
    run_git("add", "file2", cwd=str(repo2))
    run_git("commit", "-m", "commit in repo2", cwd=str(repo2))

    repo3.join("file3").write("3")
    run_git("add", "file3", cwd=str(repo3))
    run_git("commit", "-m", "commit in repo3", cwd=str(repo3))

    repo4.join("file4").write("4")
    run_git("add", "file4", cwd=str(repo4))
    run_git("commit", "-m", "commit in repo4", cwd=str(repo4))

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
            - url: ../repo3
              ref: refs/heads/main
              dir: mirror3
            - url: ../repo4
              ref: refs/heads/main
              dir: mirror4
            git_config:
              user.name: test
              user.email: tester@example.com
            """
        )
    )
    run_git("add", ".mirror-tool.yaml", cwd=str(reposuper))
    run_git("commit", "-m", "add config", cwd=str(reposuper))

    # running from top level of superproject.
    monkeypatch.chdir(str(reposuper))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "",
            "update-local",
            "--allow-empty",
            # Ask for mirrors 2 and 3 to be skipped using both CSV
            # and separate args.
            "--skip",
            "foo,mirror2,bar",
            "--skip",
            "mirror3",
        ],
    )

    # It should run OK
    entrypoint()

    # Should tell us it skipped some mirrors
    assert "Skipping update of mirror2" in caplog.text
    assert "Skipping update of mirror3" in caplog.text

    # Should tell us it's done
    assert "Mirror(s) locally updated." in caplog.text

    # Files from the updated mirrors should be present in the superproject
    assert os.path.exists(str(reposuper.join("mirror1/file1")))
    assert os.path.exists(str(reposuper.join("mirror4/file4")))

    # But NOT from the skipped mirrors.
    assert not os.path.exists(str(reposuper.join("mirror2/file2")))
    assert not os.path.exists(str(reposuper.join("mirror3/file3")))
