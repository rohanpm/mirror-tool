import sys
import textwrap

import pytest

from mirror_tool.cmd import entrypoint


def test_no_config(tmpdir, monkeypatch):
    """validate-config should fail if config file doesn't exist"""
    monkeypatch.setattr(sys, "argv", ["", "validate-config"])
    monkeypatch.chdir(str(tmpdir))
    with pytest.raises(FileNotFoundError):
        entrypoint()


def test_bad_fields_in_config(tmpdir, monkeypatch, caplog):
    """validate-config should fail if config contains unknown fields."""
    monkeypatch.setattr(sys, "argv", ["", "validate-config"])
    monkeypatch.chdir(str(tmpdir))
    tmpdir.join(".mirror-tool.yaml").write("foo: bar\n")
    with pytest.raises(SystemExit) as excinfo:
        entrypoint()

    # It should exit with this non-zero code
    assert excinfo.value.code == 80

    # It should tell us something about what went wrong
    assert "Path: <top level of config>" in caplog.text
    assert "'foo' was unexpected" in caplog.text


def test_deep_error(tmpdir, monkeypatch, caplog):
    """validate-config should fail with decent message if config several levels deep
    does not match schema.
    """
    monkeypatch.setattr(sys, "argv", ["", "validate-config"])
    monkeypatch.chdir(str(tmpdir))

    tmpdir.join(".mirror-tool.yaml").write(
        textwrap.dedent(
            """

            mirror:
            - url: https://example.com/some/repo
              ref: refs/heads/master
              dir: upstream

            commitmsg: |-
                Merge {{commits[0].revision_abbrev}} ({{commits|length}} commit(s)) to {{mirror.dir}}

                {% for commit in commits %}
                - {{ commit.revision_abbrev }} {{ commit.subject }}
                {%- endfor %}

            gitlab_merge:
                enabled: true
                src: latest
                dest: qa
                title: "Deploy to QA"
                # this is invalid due to missing leading $
                token: GITLAB_MIRROR_TOKEN
                labels:
                - deploy
                description: Automated update of dependencies.
                comment:
                    create: "please review"
                    update: "updated, please re-review"

            git_config:
                user.name: "mirror-tool"
                user.email: "noreply@example.com"
            """
        )
    )
    with pytest.raises(SystemExit) as excinfo:
        entrypoint()

    # It should exit with this non-zero code
    assert excinfo.value.code == 80

    # It should tell us exactly the wrong field
    assert "Path: gitlab_merge.token" in caplog.text
    assert "Object: GITLAB_MIRROR_TOKEN" in caplog.text
