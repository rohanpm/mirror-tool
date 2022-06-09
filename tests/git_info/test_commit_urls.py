import datetime
from dataclasses import replace

from mirror_tool.conf import Mirror
from mirror_tool.git_info import Commit, add_urls

SAMPLE_COMMIT = Commit(
    revision="55810cd62082f26ec39a9df332af1aa9db6e6b91",
    revision_abbrev="55810cd",
    author_name="Rohan McGovern",
    author_email="rohan@mcgovern.id.au",
    author_email_local="rohan",
    author_datetime=datetime.datetime(2022, 6, 6, 22, 33, 34),
    committer_name="GitHub",
    committer_email="noreply@github.com",
    committer_email_local="noreply",
    committer_datetime=datetime.datetime(2022, 6, 6, 22, 33, 34),
    subject="Merge pull request #33 from rohanpm/empty-log",
    body="Fix a crash when commit log has an empty entry",
)


def test_github_urls():
    mirror = Mirror(url="https://github.com/example/repo", ref="refs/heads/main")
    commits = [
        replace(SAMPLE_COMMIT, revision="a1b2c3"),
        replace(SAMPLE_COMMIT, revision="aabbcc"),
    ]
    add_urls(mirror, commits)

    assert commits[0].url == "https://github.com/example/repo/commit/a1b2c3"
    assert commits[1].url == "https://github.com/example/repo/commit/aabbcc"


def test_gitlab_urls():
    mirror = Mirror(
        url="https://gitlab.example.com/example/repo", ref="refs/heads/main"
    )
    commits = [
        replace(SAMPLE_COMMIT, revision="a1b2c3"),
        replace(SAMPLE_COMMIT, revision="aabbcc"),
    ]
    add_urls(mirror, commits)

    assert commits[0].url == "https://gitlab.example.com/example/repo/-/commit/a1b2c3"
    assert commits[1].url == "https://gitlab.example.com/example/repo/-/commit/aabbcc"
