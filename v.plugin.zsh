# v: editor-oriented file selection for zsh.

typeset -g _V_PLUGIN_DIR="${${(%):-%x}:A:h}"
typeset -g _V_VFIND="${_V_PLUGIN_DIR}/bin/vfind"

fpath=("${_V_PLUGIN_DIR}/completions" $fpath)
unalias v 2>/dev/null || true
unalias vfind 2>/dev/null || true
unalias vpy 2>/dev/null || true

vfind() {
  "$_V_VFIND" "$@"
}

_v_has_selection_args() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      -t|--type|-g|--group|--include-init|--novcsignore|--no-vcsignore|--vcsignore|--no-noise|--noise|--recursive|--no-recursive)
        return 0
        ;;
    esac
  done
  return 1
}

v() {
  local -a editor_cmd
  editor_cmd=("${(@z)${EDITOR:-nvim}}")

  case "${1:-}" in
    -h|--help|--list-groups)
      "$_V_VFIND" "$@"
      return $?
      ;;
  esac

  if (( $# == 0 )) || ! _v_has_selection_args "$@"; then
    command "${editor_cmd[@]}" "$@"
    return $?
  fi

  local -a files
  files=("${(@f)$("$_V_VFIND" "$@")}")
  local vfind_status=$?
  if (( vfind_status != 0 )); then
    return $vfind_status
  fi
  if (( ${#files} == 0 )); then
    print -u2 -- "v: no matching files"
    return 1
  fi

  command "${editor_cmd[@]}" "${files[@]}"
}

vpy() {
  v --type py "$@"
}

_v_type_groups() {
  "$_V_VFIND" --list-groups 2>/dev/null
}
