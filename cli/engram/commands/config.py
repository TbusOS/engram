"""``engram config`` — read and write ``~/.engram/config.toml``.

Dotted keys address nested TOML tables: ``ui.theme`` means ``[ui]`` table,
``theme`` key. Values passed from the CLI are auto-coerced (``true`` / ``42``
/ ``3.14`` → typed), so ``engram config set budget.tokens 4096`` stores an
integer in the TOML file. Writes are atomic via
:func:`engram.core.fs.write_atomic` so a crashed ``set`` cannot leave the
file in a half-written state.

v0.2 does not define a strict config schema — callers set any key they want.
Future milestones will introduce specific keys (e.g., adapter defaults,
embedding model selection); they layer validation on top of this command
family without changing the storage shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import tomli
import tomli_w

from engram.cli import GlobalConfig
from engram.core.fs import write_atomic
from engram.core.paths import user_root

__all__ = [
    "ConfigKeyError",
    "config_group",
    "config_path",
    "get_config_value",
    "parse_value",
    "set_config_value",
]


class ConfigKeyError(KeyError):
    """Raised when a dotted config key is not present."""


def config_path() -> Path:
    """Return the absolute path to the user-global config file."""
    return user_root() / "config.toml"


def _load() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    return tomli.loads(path.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    path = config_path()
    write_atomic(path, tomli_w.dumps(data))


def parse_value(raw: str) -> Any:
    """Coerce a CLI string into int / float / bool / str.

    Preserves quoted / ambiguous strings as-is (e.g. ``"42.0.1"`` stays a
    string). Callers who need to store a literal string like ``"true"`` can
    pre-quote in their shell; v0.2 does not add a ``--string`` escape hatch
    because the use case is rare and explicit quoting is the Unix idiom.
    """
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def get_config_value(key: str) -> Any:
    """Read a dotted config key. Raises :class:`ConfigKeyError` if not found."""
    data = _load()
    cursor: Any = data
    for part in key.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise ConfigKeyError(f"config key not found: {key}")
        cursor = cursor[part]
    return cursor


def set_config_value(key: str, value: Any) -> None:
    """Write a dotted config key. Creates intermediate tables as needed.

    Raises :class:`ValueError` when an intermediate segment already exists as
    a scalar (e.g. setting ``ui.theme`` when ``ui`` is already a string).
    """
    data = _load()
    parts = key.split(".")
    cursor: dict[str, Any] = data
    for part in parts[:-1]:
        if part not in cursor:
            cursor[part] = {}
        elif not isinstance(cursor[part], dict):
            raise ValueError(f"cannot set `{key}`: intermediate segment `{part}` is not a table")
        cursor = cursor[part]
    cursor[parts[-1]] = value
    _save(data)


def _flatten(prefix: str, value: Any) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, Any]] = []
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else k
            out.extend(_flatten(child, v))
        return out
    return [(prefix, value)]


# ------------------------------------------------------------------
# click group
# ------------------------------------------------------------------


@click.group("config")
def config_group() -> None:
    """Read and write the user-global engram config at ~/.engram/config.toml."""


@config_group.command("get")
@click.argument("key")
@click.pass_obj
def _get(cfg: GlobalConfig, key: str) -> None:
    """Print the value at KEY (dotted path like ``ui.theme``)."""
    try:
        value = get_config_value(key)
    except ConfigKeyError as exc:
        raise click.ClickException(str(exc)) from exc
    if cfg.output_format == "json":
        click.echo(json.dumps({"key": key, "value": value}))
    else:
        click.echo(value if isinstance(value, str) else json.dumps(value))


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_obj
def _set(cfg: GlobalConfig, key: str, value: str) -> None:
    """Write VALUE to KEY (auto-coerced to int/float/bool when parseable)."""
    typed = parse_value(value)
    try:
        set_config_value(key, typed)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if cfg.output_format == "json":
        click.echo(json.dumps({"key": key, "value": typed}))
    else:
        click.echo(f"set {key} = {typed!r}")


@config_group.command("list")
@click.pass_obj
def _list(cfg: GlobalConfig) -> None:
    """Print every key = value pair currently stored."""
    data = _load()
    if cfg.output_format == "json":
        click.echo(json.dumps(data))
        return
    for k, v in sorted(_flatten("", data)):
        click.echo(f"{k} = {v!r}")
