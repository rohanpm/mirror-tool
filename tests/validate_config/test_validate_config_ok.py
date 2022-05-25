import sys
import textwrap

from mirror_tool.cmd import entrypoint


def test_valid_nomirror_config(tmpdir, monkeypatch):
    """validate-config should succeed on mostly empty config file."""
    monkeypatch.setattr(sys, "argv", ["", "validate-config"])
    monkeypatch.chdir(str(tmpdir))
    tmpdir.join(".mirror-tool.yaml").write("mirror: []\n")
    entrypoint()


def test_valid_typical_config(tmpdir, monkeypatch):
    """validate-config should succeed on a more complex file using
    all available options.
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
                token: $GITLAB_MIRROR_TOKEN
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
    entrypoint()
