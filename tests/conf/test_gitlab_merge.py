import pytest

from mirror_tool.conf import GitlabMerge


def test_bad_token():
    """Token in config must be declared as some env var reference."""
    merge = GitlabMerge(token="whatever")
    with pytest.raises(ValueError, match=r"Must be of form '\$ENV_VAR_NAME'"):
        merge.token_final


def test_token_missing_in_env():
    """Env var referenced by token must be defined."""
    merge = GitlabMerge(token="$SOME_ENV_VAR_NOT_SET")
    with pytest.raises(
        ValueError, match=r"GitLab token not available in \$SOME_ENV_VAR_NOT_SET"
    ):
        merge.token_final


def test_url_token_usage(monkeypatch):
    """Token is used in URL only in cases where it makes sense to do so."""

    merge = GitlabMerge(token="$FAKE_TOKEN")
    monkeypatch.setenv("FAKE_TOKEN", "not-a-real-token")

    # Not HTTPS => no usage of token
    merge.push_url = "ssh://host.example.com/somerepo"
    assert merge.push_url_final == "ssh://host.example.com/somerepo"

    # HTTPS but has auth already set => no usage of token
    merge.push_url = "https://user:pass@host.example.com/somerepo"
    assert merge.push_url_final == "https://user:pass@host.example.com/somerepo"

    # HTTPS with no auth => now the token comes into play
    merge.push_url = "https://host.example.com/somerepo"
    assert (
        merge.push_url_final
        == "https://token:not-a-real-token@host.example.com/somerepo"
    )
