import datetime
import subprocess

from mirror_tool.conf import Mirror
from mirror_tool.git_info import Commit, get_update_info

# Typical log of 5 commits
SAMPLE_LOG = b"""55810cd62082f26ec39a9df332af1aa9db6e6b91
55810cd
Rohan McGovern
rohan@mcgovern.id.au
rohan
1654554814
GitHub
noreply@github.com
noreply
1654554814
Merge pull request #33 from rohanpm/empty-log
Fix a crash when commit log has an empty entry\x00c0f6d49c6eea6992abed7c7f166154f8fc42b4d4
c0f6d49
Rohan McGovern
rohan@mcgovern.id.au
rohan
1654554602
Rohan McGovern
rohan@mcgovern.id.au
rohan
1654554630
Fix a crash when commit log has an empty entry
\x00a474ee8c3243a3dccce629e9637284c33a079db6
a474ee8
Renovate Bot
bot@renovateapp.com
bot
1653595872
renovate[bot]
29139614+renovate[bot]@users.noreply.github.com
29139614+renovate[bot]
1653607152
Update registry.fedoraproject.org/fedora-minimal digest to 0ddce24
\x00f181907db7476bb977d944b62b7b4ea81b7217cb
f181907
Rohan McGovern
rohan@mcgovern.id.au
rohan
1653526783
GitHub
noreply@github.com
noreply
1653526783
Merge pull request #30 from rohanpm/improve-readme
Improve README and package metadata\x001e4324eef7b783657b5e9b7d06bbd78bd32b934f
1e4324e
Rohan McGovern
rohan@mcgovern.id.au
rohan
1653526538
Rohan McGovern
rohan@mcgovern.id.au
rohan
1653526554
Improve README and package metadata
"""


def test_get_update_info_limits(monkeypatch):
    def return_sample_log(*args, **kwargs):
        return SAMPLE_LOG

    monkeypatch.setattr(subprocess, "check_output", return_sample_log)

    mirror = Mirror(url="https://example.com", ref="refs/heads/main")

    # If I get an update with limit large enough to fit all...
    update_all = get_update_info("a", mirror, commit_limit=50)

    # I should get all the commits
    assert len(update_all.commits) == 5
    assert update_all.commit_count == 5
    assert update_all.commit_elided_count == 0

    # With the commits listed in log order
    assert update_all.commits[0] == Commit(
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

    # But if I now limit the number of commits...
    update_limit = get_update_info("a", mirror, commit_limit=2)

    # I should get the limited number of commits
    assert len(update_limit.commits) == 2
    assert update_limit.commit_count == 5
    assert update_limit.commit_elided_count == 3

    # The generated commits should be in the same order as with no limit
    assert update_limit.commits == update_all.commits[:2]
