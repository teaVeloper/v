# v

Zsh plugin for a lazy-dev editor experience.

`v` is an editor wrapper around a fast file finder:

- `v` with no arguments opens `${EDITOR:-nvim}`.
- `v some-file.py` opens the editor with the given arguments unchanged.
- `v --type py src tests` opens matching files returned by `vfind`.
- `vpy src` is a convenience wrapper for `v --type py src`.
- `vfind` prints the selected files and can be used directly in scripts.

The implementation is intentionally split:

- zsh owns the interactive command shape, completion, and editor invocation.
- Python owns config parsing and `fd` command construction.
- `fd` owns the actual search, including VCS ignore behavior.

## Usage

```zsh
v
v README.md
v --type py src tests
v --type py,md .
v --group web app
v --include-init --type py .
v --novcsignore --type py .
v --no-noise --type py .
vpy .
vfind --group web --null app
```

Selection is recursive by default. Use `--no-recursive` for a shallow search.

VCS ignore files are honored by default. Use `--novcsignore` or
`--no-vcsignore` to ask `fd` to ignore VCS ignore rules.

## Config

Global config:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/v/config.toml
```

Project config:

```text
.v.toml
```

Project config is discovered from the current directory upward until the first
Git boundary. It extends global config: type groups merge by name, while scalar
defaults override earlier values.

Example:

```toml
[defaults]
recursive = true
vcsignore = true
noise = true

[types]
py = ["py"]
docs = ["md", "markdown", "rst"]
web = ["js", "ts", "tsx", "jsx", "css", "html"]

[noise]
dirs = ["site", ".cache"]
files = []
globs = ["*.generated.py"]
```

Built-in conservative noise excludes common cache/build/vendor directories and
Python `__init__.py`. To include `__init__.py` for one invocation:

```zsh
v --include-init --type py .
```

To disable a built-in noise rule in TOML:

```toml
[noise]
disable = ["python-init"]
```

Available built-in rule names:

- `python-init`
- `cache-dirs`

## Install

With antidote or any plugin loader that sources local zsh plugins, source:

```zsh
/path/to/v/v.plugin.zsh
```

The plugin exposes `v`, `vpy`, and `vfind`, and adds its completion directory to
`fpath` before `compinit`.

## Development

Run tests:

```bash
python -m unittest discover -s tests
```

Run shell syntax checks:

```bash
zsh -n v.plugin.zsh
zsh -n completions/_v
zsh -n completions/_vfind
```
