from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]


CACHE_DIRS = [
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "dist",
    "build",
]

BUILTIN_CONFIG: dict[str, Any] = {
    "defaults": {
        "editor": "",
        "recursive": True,
        "vcsignore": True,
        "noise": True,
    },
    "types": {
        "py": ["py"],
        "md": ["md", "markdown"],
        "web": ["js", "ts", "tsx", "jsx", "css", "html"],
    },
    "noise": {
        "disable": [],
        "dirs": CACHE_DIRS,
        "files": ["__init__.py"],
        "globs": [],
    },
}

BUILTIN_RULES = {
    "cache-dirs": {"dirs": CACHE_DIRS, "files": [], "globs": []},
    "python-init": {"dirs": [], "files": ["__init__.py"], "globs": []},
}


class VfindError(RuntimeError):
    pass


def _xdg_config_home() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".config"


def global_config_path() -> Path:
    return _xdg_config_home() / "v" / "config.toml"


def _is_repo_boundary(path: Path) -> bool:
    return (path / ".git").exists()


def project_config_path(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        config = candidate / ".v.toml"
        if config.exists():
            return config
        if _is_repo_boundary(candidate):
            return None
    return None


def _read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise VfindError("vfind requires Python 3.11+ for TOML config support")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise VfindError(f"invalid TOML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise VfindError(f"{path} must contain a TOML table")
    return data


def _as_string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise VfindError(f"{field} must be a string or list of strings")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise VfindError(f"{field} must contain only strings")
        result.append(item)
    return result


def _append_unique(items: list[str], values: list[str]) -> list[str]:
    result = list(items)
    seen = set(result)
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _remove_rule(config: dict[str, Any], rule_name: str) -> None:
    rule = BUILTIN_RULES.get(rule_name)
    if rule is None:
        raise VfindError(f"unknown built-in noise rule: {rule_name}")
    noise = config["noise"]
    for key in ("dirs", "files", "globs"):
        remove = set(rule[key])
        noise[key] = [item for item in noise[key] if item not in remove]


def merge_config(base: dict[str, Any], extra: dict[str, Any], *, source: Path) -> dict[str, Any]:
    config = deepcopy(base)

    defaults = extra.get("defaults", {})
    if defaults:
        if not isinstance(defaults, dict):
            raise VfindError(f"{source}: [defaults] must be a table")
        for key in ("editor", "recursive", "vcsignore", "noise"):
            if key in defaults:
                config["defaults"][key] = defaults[key]

    types = extra.get("types", {})
    if types:
        if not isinstance(types, dict):
            raise VfindError(f"{source}: [types] must be a table")
        for key, value in types.items():
            config["types"][str(key)] = _as_string_list(value, field=f"{source}: types.{key}")

    noise = extra.get("noise", {})
    if noise:
        if not isinstance(noise, dict):
            raise VfindError(f"{source}: [noise] must be a table")
        for rule in _as_string_list(noise.get("disable"), field=f"{source}: noise.disable"):
            _remove_rule(config, rule)
        for key in ("dirs", "files", "globs"):
            config["noise"][key] = _append_unique(
                config["noise"][key],
                _as_string_list(noise.get(key), field=f"{source}: noise.{key}"),
            )

    return config


def load_config(start: Path | None = None) -> dict[str, Any]:
    config = deepcopy(BUILTIN_CONFIG)
    global_path = global_config_path()
    if global_path.exists():
        config = merge_config(config, _read_toml(global_path), source=global_path)
    project_path = project_config_path(start)
    if project_path is not None:
        config = merge_config(config, _read_toml(project_path), source=project_path)
    return config


def _split_values(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for item in value.replace(",", " ").split():
            stripped = item.strip().lstrip(".")
            if stripped:
                result.append(stripped)
    return result


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def resolve_extensions(config: dict[str, Any], type_values: list[str] | None, groups: list[str] | None) -> list[str]:
    aliases = config["types"]
    extensions: list[str] = []

    for value in _split_values(type_values):
        if value in aliases:
            extensions.extend(_as_string_list(aliases[value], field=f"types.{value}"))
        else:
            extensions.append(value)

    for group in _split_values(groups):
        if group not in aliases:
            raise VfindError(f"unknown type group: {group}")
        extensions.extend(_as_string_list(aliases[group], field=f"types.{group}"))

    if not extensions:
        extensions.extend(_as_string_list(aliases.get("py", ["py"]), field="types.py"))

    return _dedupe([item.lstrip(".") for item in extensions if item.strip()])


def fd_backend() -> str:
    override = os.environ.get("V_FD")
    if override:
        return override
    for candidate in ("fd", "fdfind"):
        found = shutil.which(candidate)
        if found:
            return found
    raise VfindError("fd is required: install fd or set V_FD to a compatible executable")


def build_fd_args(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    command = [fd_backend(), "--type", "f"]

    if args.null:
        command.append("--print0")

    recursive = bool(config["defaults"].get("recursive", True))
    if args.recursive is not None:
        recursive = args.recursive
    if not recursive:
        command.extend(["--max-depth", "1"])

    vcsignore = bool(config["defaults"].get("vcsignore", True))
    if args.vcsignore is not None:
        vcsignore = args.vcsignore
    if not vcsignore:
        command.append("--no-ignore-vcs")

    for extension in resolve_extensions(config, args.type, args.group):
        command.extend(["-e", extension])

    use_noise = bool(config["defaults"].get("noise", True))
    if args.noise is not None:
        use_noise = args.noise
    if use_noise:
        noise = config["noise"]
        files = list(noise.get("files", []))
        if args.include_init and "__init__.py" in files:
            files.remove("__init__.py")
        for value in [*noise.get("dirs", []), *files, *noise.get("globs", [])]:
            command.extend(["-E", str(value)])

    paths = args.paths or ["."]
    command.extend([".", *paths])
    return command


def parser() -> argparse.ArgumentParser:
    parser_ = argparse.ArgumentParser(
        prog="vfind",
        description="Find files for the v editor plugin.",
    )
    parser_.add_argument("paths", nargs="*", help="directories to search; defaults to cwd")
    parser_.add_argument("-t", "--type", action="append", help="extension or configured type alias")
    parser_.add_argument("-g", "--group", action="append", help="configured type group")
    parser_.add_argument("--include-init", action="store_true", help="include Python __init__.py files")
    parser_.add_argument("--novcsignore", "--no-vcsignore", dest="vcsignore", action="store_false")
    parser_.add_argument("--vcsignore", dest="vcsignore", action="store_true")
    parser_.add_argument("--no-noise", dest="noise", action="store_false")
    parser_.add_argument("--noise", dest="noise", action="store_true")
    parser_.add_argument("--recursive", dest="recursive", action="store_true")
    parser_.add_argument("--no-recursive", dest="recursive", action="store_false")
    parser_.add_argument("--null", action="store_true", help="print NUL-delimited paths")
    parser_.add_argument("--list-groups", action="store_true", help="print configured type groups")
    parser_.set_defaults(vcsignore=None, noise=None, recursive=None)
    return parser_


def main(argv: list[str] | None = None) -> int:
    parsed = parser().parse_args(argv)
    try:
        config = load_config()
        if parsed.list_groups:
            for name in sorted(config["types"]):
                print(name)
            return 0
        command = build_fd_args(parsed, config)
        return subprocess.run(command, check=False).returncode
    except VfindError as exc:
        print(f"vfind: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

