from dataclasses import dataclass


@dataclass
class Mirror:
    url: str
    ref: str
    dir: str = "upstream"
