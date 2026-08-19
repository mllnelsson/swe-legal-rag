#!/usr/bin/env python3
"""Decide whether one Bash command may write to a protected Postgres database.

Reads the command text on stdin. Prints a `PreToolUse` deny document when the
command could mutate a database that is not the agent's scratch copy; prints
nothing when the command is allowed. Exits 0 either way — `db-guard.sh` reads
*output*, not exit status, as the verdict, and denies on its own if this script
fails to run at all.

The shape is a chain of cases with early exits, one per way a connection target
can be declared, because that is the only honest way to answer "which database
is this?": `psql` takes it from `-d`, a bare positional, a URI, a keyword/value
conninfo, `PGDATABASE`, `PGSERVICE`, or a fallback to `$USER`, and four of those
never name the database in the command line at all.

Every unknown resolves to *protected*. A command this parser cannot read is
exactly the command the guard exists for.

A host without a Postgres client reaches the database only through the
container, so `docker exec … psql …` and `sh -c '…'` are unwrapped and their
inner command judged on its own. The host environment deliberately does not
follow a command inside a container: `PGDATABASE` is set to the sandbox out
here and unset in there, and believing it would read a write to the development
database as a write to the scratch copy.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass, replace
from enum import StrEnum, auto
from pathlib import Path
from urllib.parse import urlsplit

# A database is scratch — free to destroy — when its name says so. Matching on
# the suffix rather than on one hardcoded name keeps the rule true if the
# development database is ever renamed: the sandbox and the test database follow
# the name, everything else stays protected by default.
SANDBOX_DATABASE_SUFFIX = "_coding_agent"
TEST_DATABASE_SUFFIX = "_test"

# libpq's own fallback chain when nothing names a database.
DATABASE_ENVIRONMENT_VARIABLE = "PGDATABASE"
USERNAME_ENVIRONMENT_VARIABLES = ("PGUSER", "USER")
SERVICE_ENVIRONMENT_VARIABLE = "PGSERVICE"
SERVICE_FILE_ENVIRONMENT_VARIABLE = "PGSERVICEFILE"
DEFAULT_SERVICE_FILE = Path.home() / ".pg_service.conf"

# An empty host means the unix socket, which cannot leave this machine.
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})
POSTGRES_URI_SCHEMES = frozenset({"postgres", "postgresql"})

SHELL_SEPARATORS = frozenset({";", "&&", "||", "&", "\n"})
PIPE = "|"
INPUT_REDIRECTIONS = frozenset({"<", "<<", "<<<"})

INLINE_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
CONNECT_METACOMMAND_RE = re.compile(r"\\c(?:onnect)?\s+(\S+)")
SQL_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
SQL_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# A fragment must *start* with one of these to be considered readable...
READ_ONLY_START_RE = re.compile(
    r"^(select|with|show|table|values|explain)\b", re.IGNORECASE
)

# ...and must contain none of these anywhere, which is what catches a write
# hidden behind a CTE: `WITH x AS (SELECT 1) DELETE FROM entities` opens with an
# allowlisted keyword and is still a delete. Both checks must pass, so a write
# form nobody thought of fails closed rather than sailing through.
WRITE_KEYWORDS = (
    "alter",
    "analyze",
    "begin",
    "call",
    "checkpoint",
    "cluster",
    "comment",
    "commit",
    "copy",
    "create",
    "deallocate",
    "declare",
    "delete",
    "discard",
    "do",
    "drop",
    "end",
    "execute",
    "fetch",
    "grant",
    "import",
    "insert",
    "listen",
    "load",
    "lock",
    "merge",
    "move",
    "notify",
    "prepare",
    "reassign",
    "refresh",
    "reindex",
    "release",
    "reset",
    "revoke",
    "rollback",
    "savepoint",
    "security",
    "set",
    "start",
    "truncate",
    "unlisten",
    "update",
    "vacuum",
)
WRITE_KEYWORD_RE = re.compile(r"\b(" + "|".join(WRITE_KEYWORDS) + r")\b", re.IGNORECASE)

# Backslash metacommands that only describe or format. `\c` switches database,
# `\i` runs a file, `\copy` writes rows and `\gexec` executes whatever the last
# query produced — none of them appear here.
READ_ONLY_METACOMMAND_RE = re.compile(
    r"^\\(d[a-zA-Z+]*|l\+?|z|x|timing|pset|a|t|f|H|\?|conninfo|encoding|echo)\b"
)


class ToolKind(StrEnum):
    """What a Postgres command-line tool does to the database it connects to."""

    PSQL = auto()
    DROP_DATABASE = auto()
    CREATE_DATABASE = auto()
    READS_ONLY = auto()
    WRITES = auto()


TOOL_KINDS = {
    "psql": ToolKind.PSQL,
    "dropdb": ToolKind.DROP_DATABASE,
    "createdb": ToolKind.CREATE_DATABASE,
    "pg_dump": ToolKind.READS_ONLY,
    "pg_dumpall": ToolKind.READS_ONLY,
    "pg_restore": ToolKind.WRITES,
    "vacuumdb": ToolKind.WRITES,
    "reindexdb": ToolKind.WRITES,
    "clusterdb": ToolKind.WRITES,
    "createuser": ToolKind.WRITES,
    "dropuser": ToolKind.WRITES,
}

# A tool name sitting where a command goes: at the start of the line, after a
# separator or a pipe, inside a substitution, optionally behind `VAR=value`
# prefixes and a directory path. Used only when tokenising fails, to tell a line
# that *runs* psql from one that merely says the word.
COMMAND_POSITION = (
    r"(?:^|[|;&\n]|\$\()\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:[\w./-]*/)?"
)
TOOL_ALTERNATION = "|".join(TOOL_KINDS)
TOOL_IN_COMMAND_POSITION_RE = re.compile(
    COMMAND_POSITION + r"(?:" + TOOL_ALTERNATION + r")\b"
)

# Tools that run a command somewhere this parser has to follow it to: a
# container, or a nested shell. Neither appears in `TOOL_KINDS` — they touch no
# database themselves, they only carry something that does.
CONTAINER_TOOLS = frozenset({"docker", "podman", "docker-compose", "podman-compose"})
SHELL_TOOLS = frozenset({"sh", "bash", "zsh", "dash", "ash"})

# Words that stand between `docker` and the subcommand, and the subcommands that
# take a container/service/image followed by a command to run in it.
CONTAINER_GROUP_WORDS = frozenset({"compose", "container"})
CONTAINER_EXEC_SUBCOMMANDS = frozenset({"exec", "run"})

# Options consuming the token after them, on either side of the subcommand.
# Getting this wrong shifts the container name by one and unwraps the wrong
# argument list, so the set is deliberately generous: an option wrongly listed
# here costs a fail-closed refusal, one wrongly missing costs a miss.
CONTAINER_VALUE_OPTIONS = frozenset(
    {
        "-H", "--host", "-c", "--context", "-l", "--log-level",
        "-f", "--file", "-p", "--project-name", "--project-directory",
        "--profile", "--env-file", "--progress", "--ansi", "--parallel",
        "-e", "--env", "-u", "--user", "-w", "--workdir",
        "--index", "--detach-keys", "--name", "--network", "--entrypoint",
        "-v", "--volume", "--label", "--publish",
    }
)  # fmt: skip
CONTAINER_ENVIRONMENT_OPTIONS = frozenset({"-e", "--env"})

# A Postgres tool reached through a container, for the same tokenising-failed
# fallback: `docker exec db psql …` puts psql where no command-position rule
# would find it.
TOOL_BEHIND_CONTAINER_RE = re.compile(
    COMMAND_POSITION
    + r"(?:"
    + "|".join(sorted(CONTAINER_TOOLS))
    + r")\b[^|;&\n]*?\b(?:"
    + TOOL_ALTERNATION
    + r")\b"
)

IGNORED_OPTION = "_ignored"
SHORT_OPTION_NAMES = {
    "c": "command",
    "d": "dbname",
    "f": "file",
    "h": "host",
    "T": "template",
}


@dataclass(frozen=True)
class OptionSpec:
    """Which options of a tool consume the argument that follows them.

    Only this matters for parsing: an option that takes a value hides the next
    token, and a token that is not hidden is a positional — which is how `psql
    overklagan` names its database.
    """

    short_with_value: str
    long_with_value: frozenset[str]


PSQL_OPTIONS = OptionSpec(
    short_with_value="cdfvoFRLPhpUT",
    long_with_value=frozenset(
        {
            "command",
            "dbname",
            "file",
            "set",
            "variable",
            "output",
            "field-separator",
            "record-separator",
            "log-file",
            "pset",
            "host",
            "port",
            "username",
            "table-attr",
        }
    ),
)

UTILITY_OPTIONS = OptionSpec(
    short_with_value="hpUdfFTEDlOjZSn",
    long_with_value=frozenset(
        {
            "host",
            "port",
            "username",
            "maintenance-db",
            "dbname",
            "file",
            "format",
            "template",
            "encoding",
            "tablespace",
            "locale",
            "owner",
            "lc-collate",
            "lc-ctype",
            "jobs",
            "compress",
            "schema",
            "table",
            "superuser",
        }
    ),
)

# A shell carries its command in `-c`, which is all this parser wants from it.
SHELL_OPTIONS = OptionSpec(short_with_value="c", long_with_value=frozenset())


@dataclass(frozen=True)
class Segment:
    """One command in a shell line, and where its standard input comes from.

    `host_environment_applies` is false once the command has been unwrapped out
    of a container: `PGDATABASE` and friends belong to this machine, not to the
    process that would actually run, and inheriting them there would resolve an
    unnamed database to the sandbox when the container's own default is the
    development database.
    """

    argv: list[str]
    environment: dict[str, str]
    stdin_is_opaque: bool
    host_environment_applies: bool = True


@dataclass(frozen=True)
class Connection:
    """The databases a command would touch, and the host they live on.

    `databases` can hold more than one because `\\c` switches mid-session, and
    a command that reaches two databases is as protected as its most protected
    one. `resolved` is false when no case in the chain could decide.
    """

    databases: tuple[str, ...]
    host: str
    resolved: bool


UNRESOLVED = Connection(databases=(), host="", resolved=False)


def is_scratch_database(name: str) -> bool:
    """Whether this database is one the agent may destroy freely."""
    return name.endswith(SANDBOX_DATABASE_SUFFIX) or name.endswith(TEST_DATABASE_SUFFIX)


def is_protected(connection: Connection) -> bool:
    """Whether a write through this connection has to be refused."""
    if not connection.resolved or not connection.databases:
        return True
    if connection.host.lower() not in LOCAL_HOSTS and not connection.host.startswith(
        "/"
    ):
        return True
    return any(not is_scratch_database(name) for name in connection.databases)


def split_segments(tokens: list[str]) -> list[Segment]:
    """Break a tokenised shell line into the individual commands it runs.

    A command downstream of a pipe is marked opaque: its SQL arrives on standard
    input, where this parser cannot read it.
    """
    segments: list[Segment] = []
    current: list[str] = []
    fed_by_pipe = False

    def flush(next_is_piped: bool) -> None:
        nonlocal current, fed_by_pipe
        if current:
            environment, argv = split_inline_environment(current)
            segments.append(
                Segment(
                    argv=argv,
                    environment=environment,
                    stdin_is_opaque=fed_by_pipe
                    or any(token in INPUT_REDIRECTIONS for token in current),
                )
            )
        current = []
        fed_by_pipe = next_is_piped

    for token in tokens:
        if token in SHELL_SEPARATORS:
            flush(False)
        elif token == PIPE:
            flush(True)
        else:
            current.append(token)
    flush(False)
    return segments


def split_inline_environment(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    """Peel `VAR=value` assignments off the front of a command."""
    environment: dict[str, str] = {}
    for position, token in enumerate(tokens):
        if not INLINE_ASSIGNMENT_RE.match(token):
            return environment, tokens[position:]
        name, _, value = token.partition("=")
        environment[name] = value
    return environment, []


def parse_arguments(
    argv: list[str], spec: OptionSpec
) -> tuple[dict[str, list[str]], list[str]]:
    """Split a tool's arguments into option values and positionals."""
    values: dict[str, list[str]] = {}
    positionals: list[str] = []

    def record(name: str, value: str) -> None:
        values.setdefault(name, []).append(value)

    index = 0
    while index < len(argv):
        token = argv[index]
        index += 1
        if token == "--":
            positionals.extend(argv[index:])
            break
        if token.startswith("--"):
            name, separator, inline = token[2:].partition("=")
            if name not in spec.long_with_value:
                continue
            if separator:
                record(name, inline)
            elif index < len(argv):
                record(name, argv[index])
                index += 1
            continue
        if token.startswith("-") and len(token) > 1:
            letters = token[1:]
            while letters:
                letter, letters = letters[0], letters[1:]
                if letter not in spec.short_with_value:
                    continue
                name = SHORT_OPTION_NAMES.get(letter, IGNORED_OPTION)
                if letters:
                    record(name, letters)
                    letters = ""
                elif index < len(argv):
                    record(name, argv[index])
                    index += 1
            continue
        positionals.append(token)
    return values, positionals


def database_from_uri(text: str) -> tuple[str, str] | None:
    """The `(database, host)` a `postgresql://` URI points at."""
    parts = urlsplit(text)
    if parts.scheme not in POSTGRES_URI_SCHEMES:
        return None
    return parts.path.lstrip("/"), parts.hostname or ""


def database_from_conninfo(text: str) -> tuple[str, str] | None:
    """The `(database, host)` a `key=value ...` conninfo string points at."""
    if "=" not in text:
        return None
    settings = dict(item.split("=", 1) for item in text.split() if item.count("=") >= 1)
    if "dbname" not in settings and "service" not in settings:
        return None
    database = settings.get("dbname") or database_from_service(
        settings.get("service", "")
    )
    return (database or "", settings.get("host", ""))


def database_from_service(name: str) -> str:
    """The `dbname` a named connection service resolves to, if it can be read."""
    if not name:
        return ""
    override = os.environ.get(SERVICE_FILE_ENVIRONMENT_VARIABLE)
    service_file = Path(override) if override else DEFAULT_SERVICE_FILE
    try:
        lines = service_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped == f"[{name}]"
        elif in_section and stripped.startswith("dbname"):
            return stripped.partition("=")[2].strip()
    return ""


def database_from_any_form(text: str) -> tuple[str, str] | None:
    """Read a connection target out of whichever form `text` happens to be."""
    return database_from_uri(text) or database_from_conninfo(text)


def resolve_psql_connection(
    values: dict[str, list[str]], positionals: list[str], segment: Segment
) -> Connection:
    """Work out which database a `psql` invocation would connect to.

    The cases are ordered the way libpq itself resolves them, and the first one
    that produces a name wins.
    """
    host = values.get("host", [""])[-1]

    # Case: `-d` / `--dbname`, whose value may itself be a URI or a conninfo.
    for candidate in values.get("dbname", []):
        parsed = database_from_any_form(candidate)
        if parsed is not None:
            return Connection((parsed[0],), parsed[1] or host, bool(parsed[0]))
        return Connection((candidate,), host, True)

    # Case: a bare positional — `psql overklagan`, `psql postgresql://…/db`.
    if positionals:
        parsed = database_from_any_form(positionals[0])
        if parsed is not None:
            return Connection((parsed[0],), parsed[1] or host, bool(parsed[0]))
        return Connection((positionals[0],), host, True)

    # Case: an assignment written in front of the command.
    inline = segment.environment.get(DATABASE_ENVIRONMENT_VARIABLE)
    if inline:
        return Connection((inline,), host, True)

    # Case: a named service, from the command's own environment or ours.
    service = segment.environment.get(SERVICE_ENVIRONMENT_VARIABLE)
    if not service and segment.host_environment_applies:
        service = os.environ.get(SERVICE_ENVIRONMENT_VARIABLE)
    if service:
        from_service = database_from_service(service)
        if not from_service:
            return UNRESOLVED
        return Connection((from_service,), host, True)

    # Case: nothing named it, so libpq falls back to PGDATABASE, then the user
    # name. This is the hole the environment layer plugs — but only for a command
    # running on this machine. Inside a container none of these variables is what
    # libpq will read there, so an unnamed database stays unresolved, which
    # `is_protected` counts as protected.
    if not segment.host_environment_applies:
        return UNRESOLVED
    from_environment = os.environ.get(DATABASE_ENVIRONMENT_VARIABLE)
    if from_environment:
        return Connection((from_environment,), host, True)
    for variable in USERNAME_ENVIRONMENT_VARIABLES:
        user = os.environ.get(variable)
        if user:
            return Connection((user,), host, True)
    return UNRESOLVED


def resolve_utility_connection(
    values: dict[str, list[str]], positionals: list[str], segment: Segment
) -> Connection:
    """Work out which database `dropdb`, `createdb`, `pg_dump`… would act on."""
    host = values.get("host", [""])[-1]
    for candidate in [*values.get("dbname", []), *positionals[:1]]:
        parsed = database_from_any_form(candidate)
        if parsed is not None:
            return Connection((parsed[0],), parsed[1] or host, bool(parsed[0]))
        return Connection((candidate,), host, True)
    inline = segment.environment.get(DATABASE_ENVIRONMENT_VARIABLE)
    if inline:
        return Connection((inline,), host, True)
    return UNRESOLVED


def databases_from_connect_metacommands(sql: str) -> tuple[str, ...]:
    """Databases a `\\c` inside the SQL would switch to."""
    return tuple(match.strip("'\"") for match in CONNECT_METACOMMAND_RE.findall(sql))


def sql_from_segment(values: dict[str, list[str]], segment: Segment) -> str | None:
    """The SQL a `psql` invocation would run, or `None` when it cannot be read.

    Unreadable covers `-f script.sql`, a redirect, a pipe, and an interactive
    session — all cases where the statements are decided somewhere this parser
    cannot look.
    """
    if segment.stdin_is_opaque or values.get("file"):
        return None
    commands = values.get("command")
    if not commands:
        return None
    return ";".join(commands)


def statement_is_read_only(sql: str) -> bool:
    """Whether every statement in `sql` only reads."""
    without_comments = SQL_BLOCK_COMMENT_RE.sub(" ", SQL_LINE_COMMENT_RE.sub(" ", sql))
    fragments = [
        fragment.strip() for fragment in without_comments.split(";") if fragment.strip()
    ]
    if not fragments:
        return False
    return all(fragment_is_read_only(fragment) for fragment in fragments)


def fragment_is_read_only(fragment: str) -> bool:
    """Whether one statement — or one backslash metacommand — only reads."""
    if fragment.startswith("\\"):
        return READ_ONLY_METACOMMAND_RE.match(fragment) is not None
    if READ_ONLY_START_RE.match(fragment) is None:
        return False
    return WRITE_KEYWORD_RE.search(fragment) is None


def describe(connection: Connection) -> str:
    """How a connection reads in a denial message."""
    if not connection.resolved:
        return "a database this guard could not identify"
    return " and ".join(connection.databases) or "an unnamed database"


def refusal(reason: str) -> str:
    """A denial, phrased as a report of what was observed.

    Deliberately not imperative: hook text shaped like a system command is what
    `py-check.sh` already warns about tripping prompt-injection defenses.
    """
    return (
        f"{reason} The development database is read-only for this session; the "
        "writable copy is the one named by PGDATABASE. A change that has to land "
        "in the development database is the user's call."
    )


def find_container_subcommand(argv: list[str]) -> int | None:
    """Index of the container/service/image in a `docker exec`-shaped command.

    Returns `None` for every other docker invocation — `docker ps`, `docker
    compose up` — none of which carries a command to look inside.
    """
    index = 1
    while index < len(argv):
        token = argv[index]
        if token.startswith("-"):
            name = token.partition("=")[0]
            takes_value = name in CONTAINER_VALUE_OPTIONS and "=" not in token
            index += 2 if takes_value else 1
            continue
        if token in CONTAINER_GROUP_WORDS:
            index += 1
            continue
        if token in CONTAINER_EXEC_SUBCOMMANDS:
            return index + 1
        return None
    return None


def unwrap_container_segment(segment: Segment) -> Segment | None:
    """The command a container invocation would run inside the container.

    Options are walked by hand rather than through `parse_arguments` because
    parsing must stop at the container name: everything after it belongs to the
    inner tool, and reading `psql -U postgres` with docker's option table would
    take `postgres` for the database.
    """
    index = find_container_subcommand(segment.argv)
    if index is None:
        return None
    environment: dict[str, str] = {}
    while index < len(segment.argv):
        token = segment.argv[index]
        if not token.startswith("-"):
            break  # the container, service or image itself
        name, separator, inline = token.partition("=")
        if name not in CONTAINER_VALUE_OPTIONS:
            index += 1  # a flag carrying no value, `-it` among them
            continue
        if separator:
            value, index = inline, index + 1
        elif index + 1 < len(segment.argv):
            value, index = segment.argv[index + 1], index + 2
        else:
            break
        if name in CONTAINER_ENVIRONMENT_OPTIONS:
            key, assigned, assignment = value.partition("=")
            if assigned:
                environment[key] = assignment
    inner = segment.argv[index + 1 :]
    if not inner:
        return None
    return Segment(
        argv=inner,
        environment=environment,
        stdin_is_opaque=segment.stdin_is_opaque,
        host_environment_applies=False,
    )


def refuse_unreadable_tool(argv: list[str], reason: str) -> str | None:
    """Refuse when a Postgres tool sits in an argument list this parser gave up on."""
    if any(Path(token).name in TOOL_KINDS for token in argv):
        return refusal(reason)
    return None


def inspect_container_segment(segment: Segment) -> str | None:
    """The reason a command run inside a container must be refused."""
    inner = unwrap_container_segment(segment)
    if inner is None:
        return refuse_unreadable_tool(
            segment.argv[1:],
            "A Postgres tool runs inside a container here, in a form this guard "
            "could not read, so the database it would reach is unknown.",
        ) or inspect_inline_environment(segment)
    reason = inspect_segment(inner)
    if reason is not None:
        return reason
    # The unwrap found a command but the dispatch only reads its first word, so a
    # tool behind a wrapper it does not model — `docker exec db env psql …` —
    # would otherwise pass unexamined.
    inner_tool = Path(inner.argv[0]).name
    if inner_tool in TOOL_KINDS or inner_tool in SHELL_TOOLS:
        return None
    return refuse_unreadable_tool(
        inner.argv,
        "A Postgres tool runs inside a container behind another command, so what "
        "it would reach is not visible to this guard.",
    )


def inspect_shell_segment(segment: Segment) -> str | None:
    """The reason a command a shell would run via `-c` must be refused."""
    values, _ = parse_arguments(segment.argv[1:], SHELL_OPTIONS)
    for payload in values.get("command", []):
        try:
            tokens = shlex.split(payload, comments=False, posix=True)
        except ValueError:
            if TOOL_IN_COMMAND_POSITION_RE.search(payload) is None:
                continue
            return refusal(
                "A shell would run a Postgres tool whose quoting could not be "
                "parsed, so the database it targets is unknown."
            )
        for nested in split_segments(tokens):
            reason = inspect_segment(
                replace(
                    nested,
                    host_environment_applies=segment.host_environment_applies,
                )
            )
            if reason is not None:
                return reason
    return None


def inspect_segment(segment: Segment) -> str | None:
    """The reason this one command must be refused, or `None` to allow it."""
    if not segment.argv:
        return None
    tool = Path(segment.argv[0]).name

    # Case: a command that runs another command somewhere else. Follow it there
    # before deciding anything, because the database is named in the inner one.
    if tool in CONTAINER_TOOLS:
        return inspect_container_segment(segment)
    if tool in SHELL_TOOLS:
        return inspect_shell_segment(segment)

    kind = TOOL_KINDS.get(tool)

    # Case: not a Postgres tool at all. An inline assignment aimed at a
    # protected database is still worth catching — `DATABASE_URL=…/overklagan
    # uv run alembic upgrade head` writes just as surely as psql does.
    if kind is None:
        return inspect_inline_environment(segment)

    if kind is ToolKind.PSQL:
        values, positionals = parse_arguments(segment.argv[1:], PSQL_OPTIONS)
        connection = resolve_psql_connection(values, positionals, segment)
        sql = sql_from_segment(values, segment)
        if sql is not None:
            switched = databases_from_connect_metacommands(sql)
            if switched:
                connection = Connection(
                    databases=connection.databases + switched,
                    host=connection.host,
                    resolved=connection.resolved,
                )
        if not is_protected(connection):
            return None
        if sql is None:
            return refusal(
                f"psql would connect to {describe(connection)} and run "
                "statements this guard cannot read — they come from a file, a "
                "redirect, a pipe, or an interactive session."
            )
        if statement_is_read_only(sql):
            return None
        return refusal(
            f"psql would run a statement that is not read-only against "
            f"{describe(connection)}."
        )

    values, positionals = parse_arguments(segment.argv[1:], UTILITY_OPTIONS)

    # Case: `createdb` names the database it *creates*, so the protected name to
    # look at is the new one, not the `-T` template it copies from.
    if kind is ToolKind.CREATE_DATABASE:
        created = positionals[0] if positionals else ""
        if created and is_scratch_database(created):
            return None
        return refusal(f"createdb would create {created or 'a database'}.")

    connection = resolve_utility_connection(values, positionals, segment)
    if not is_protected(connection):
        return None
    if kind is ToolKind.READS_ONLY:
        return None
    return refusal(f"{tool} would modify {describe(connection)}.")


def inspect_inline_environment(segment: Segment) -> str | None:
    """Refuse a non-Postgres command pointed at a protected database by env."""
    for variable, value in segment.environment.items():
        if variable == DATABASE_ENVIRONMENT_VARIABLE:
            connection = Connection((value,), "", True)
        elif variable.endswith("DATABASE_URL"):
            parsed = database_from_any_form(value)
            connection = (
                Connection((parsed[0],), parsed[1], bool(parsed[0]))
                if parsed
                else UNRESOLVED
            )
        else:
            continue
        if is_protected(connection):
            return refusal(
                f"{variable} points this command at {describe(connection)}, and "
                "what it would run there is not visible to this guard."
            )
    return None


def inspect(command: str) -> str | None:
    """The reason a Bash command must be refused, or `None` to allow it."""
    try:
        tokens = shlex.split(command, comments=False, posix=True)
    except ValueError:
        # Unbalanced quoting on its own is no evidence of a database command —
        # a commit message or a heredoc that merely mentions psql lands here,
        # and refusing those would make the guard something to route around.
        # What matters is whether a Postgres tool sits where a command goes.
        if (
            TOOL_IN_COMMAND_POSITION_RE.search(command) is None
            and TOOL_BEHIND_CONTAINER_RE.search(command) is None
        ):
            return None
        return refusal(
            "A Postgres tool is invoked in this line, but its quoting could not "
            "be parsed, so the database it targets is unknown."
        )
    for segment in split_segments(tokens):
        reason = inspect_segment(segment)
        if reason is not None:
            return reason
    return None


def main() -> int:
    command = sys.stdin.read()
    reason = inspect(command)
    if reason is None:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
