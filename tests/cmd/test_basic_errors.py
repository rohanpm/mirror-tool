import sys

import pytest

from mirror_tool.cmd import entrypoint


def test_no_subcommand(monkeypatch, caplog):
    """mirror-tool requires a subcommand."""
    monkeypatch.setattr(sys, "argv", [""])
    with pytest.raises(SystemExit) as excinfo:
        entrypoint()
    assert "Must specify a command" in caplog.text
    assert excinfo.value.code == 72
