import os
from typing import Any, Dict


def environ_with_git_config(
    git_config: Dict[str, Any], input_environ: Dict[str, str] = os.environ
) -> Dict[str, str]:
    out = input_environ.copy()
    count = int(input_environ.get("GIT_CONFIG_COUNT") or "0")

    for key, val in git_config.items():
        out[f"GIT_CONFIG_KEY_{count}"] = key
        out[f"GIT_CONFIG_VALUE_{count}"] = str(val)
        count += 1

    out["GIT_CONFIG_COUNT"] = str(count)
    return out
