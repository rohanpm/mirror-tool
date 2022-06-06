from mirror_tool.git_info import Commit


def test_empty_commits():
    """Empty entries are ignored while parsing logs."""

    commits = list(Commit.from_log(b"\x00\x00\x00"))
    assert commits == []
