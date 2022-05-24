import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Generator, List, TextIO

from .conf import Mirror

LOG = logging.getLogger("mirror-tool")


class GitParseError(RuntimeError):
    pass


@dataclass
class Commit:
    """Contains info on a single commit."""

    revision: str
    """The commit's revision (SHA1)."""

    revision_abbrev: str
    """The commit's abbreviated revision."""

    author: str
    """The commit's author, in "Full Name <email@example.com>" format."""

    committer: str
    """The commit's committer, in "Full Name <email@example.com>" format."""

    author_datetime: datetime
    """The 'author' timestamp."""

    committer_datetime: datetime
    """The 'committer' timestamp."""

    subject: str
    """The subject line from the commit message."""

    body: str = ""
    """The body of the commit message."""

    @classmethod
    def new(cls, **kwargs):
        if "revision_abbrev" not in kwargs:
            kwargs["revision_abbrev"] = kwargs["revision"][0:7]
        return cls(**kwargs)

    @classmethod
    def from_raw_log(cls, stream: TextIO) -> Generator["Commit", None, None]:
        """Yields a sequence of Commits for each commit found in the input stream,
        which should contain text of the same form produced by "git log --pretty=raw".
        """
        commit = "commit"
        subject = "subject"
        body = "body"
        fields = "fields"

        expecting = commit
        kwargs = {}

        while True:
            line = stream.readline()
            if not line:
                break

            LOG.debug("%s %s", expecting, repr(line))
            line = line.rstrip()

            if expecting is fields:
                if not line:
                    # we're at the end of fields section
                    expecting = subject
                    continue

                match = re.match(r"^([a-z0-9_]+) (.+)$", line)
                if not match:
                    raise GitParseError(
                        "expecting: 'key val' or blank line, got: %s" % repr(line)
                    )
                key = match.group(1)
                value = match.group(2)

                if key in ("author", "committer"):
                    kwargs.update(cls._parse_author(key, value))

            if expecting is subject:
                if not line:
                    # end of subject
                    expecting = body
                    continue

                if not line.startswith("    "):
                    raise GitParseError("expecting: subject, got: %s" % repr(line))

                line = line[4:]
                kwargs["subject"] = kwargs.get("subject", "") + line

            if expecting is body:
                if line.startswith("commit "):
                    # end of body and start of next commit.
                    yield Commit.new(**kwargs)
                    kwargs = {}

                    # note: NOT doing 'continue' here as we need to fall through
                    # to the next block:
                    expecting = commit
                else:
                    if line and not line.startswith("    "):
                        raise GitParseError("expecting: body, got: %s" % repr(line))
                    line = line[4:]
                    if kwargs.get("body"):
                        line = "\n" + line
                    kwargs["body"] = kwargs.get("body", "") + line

            if expecting is commit:
                if not line.startswith("commit "):
                    raise GitParseError(
                        "expecting: start of commit, got: %s" % repr(line)
                    )
                kwargs["revision"] = line[len("commit ") :]
                expecting = fields
                continue

        if kwargs:
            yield Commit.new(**kwargs)

    @classmethod
    def _parse_author(cls, key: str, value: str):
        # Initially:
        #
        # Some Person <whoever@example.com> 1652562062 -0700"""

        def revstr(x: str):
            return "".join(reversed(x))

        value = revstr(value)
        # 0070- 2602652561 >moc.elpmaxe@reveohw< nosreP emoS

        tz_rev, ts_rev, ident_rev = value.split(" ", 2)
        # ("0070-", "2602652561", ">moc.elpmaxe@reveohw< nosreP emoS")

        tz = revstr(tz_rev)
        ts = revstr(ts_rev)
        ident = revstr(ident_rev)

        offset = timedelta()
        if len(tz) == 5:
            offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
            if tz.startswith("-"):
                offset = timedelta() - offset

        when = datetime.fromtimestamp(int(ts), tz=timezone(offset))

        return {key: ident, f"{key}_datetime": when}


@dataclass
class UpdateInfo:
    """Contains info on an update for a single mirror."""

    mirror: Mirror
    """The mirror associated with this update."""

    commits: List[Commit] = field(default_factory=list)
    """The commits pulled in by the update. The first entry is the tip of the update."""

    commit_count: int = 0
    """The number of commit(s) being pulled by the update."""

    changed: bool = False
    """True if there were any changes at all."""


def get_update_info(rev_to: str, mirror: Mirror, rev_from: str = "HEAD") -> UpdateInfo:
    proc = subprocess.Popen(
        ["git", "log", "--pretty=raw", f"{rev_from}..{rev_to}"],
        text=True,
        stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    commits = list(Commit.from_raw_log(proc.stdout))
    count = len(commits)
    changed = True if count else False

    return UpdateInfo(
        mirror=mirror, changed=changed, commit_count=count, commits=commits
    )
