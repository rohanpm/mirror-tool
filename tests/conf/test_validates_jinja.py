import jsonschema
import pytest

from mirror_tool.conf import Config, GitlabPromote


def test_validates_jinja_templates():
    """Config validation covers Jinja templates."""

    conf = Config(
        {
            "gitlab_promote": [
                {"comment": {"create": "oops, not a valid {{ jinja template"}}
            ]
        }
    )

    # It should raise a ValidationError
    with pytest.raises(jsonschema.ValidationError) as exc:
        conf.validate()

    # It should tell us why
    assert "Invalid Jinja template" in str(exc)

    # And where
    assert list(exc.value.path) == ["gitlab_promote", 0, "comment", "create"]
