#!/usr/bin/env bash

set -euo pipefail

branch="${1:-$(git branch --show-current)}"

if [[ -z "${branch}" ]]; then
  echo "Unable to determine current branch." >&2
  exit 1
fi

remote_url="$(git remote get-url origin)"

if [[ "${remote_url}" != https://* ]]; then
  echo "origin remote must be an HTTPS URL for PAT push." >&2
  exit 1
fi

cached_cred="$(
  printf 'url=%s\n\n' "${remote_url}" | git credential fill 2>/dev/null || true
)"
cached_pat="$(
  printf '%s\n' "${cached_cred}" | awk -F= '/^password=/{print substr($0, 10); exit}'
)"

if [[ -n "${GITHUB_PAT:-}" ]]; then
  pat="${GITHUB_PAT}"
elif [[ -n "${cached_pat}" ]]; then
  pat="${cached_pat}"
else
  read -r -s -p "Enter GitHub PAT: " pat
  echo
fi

if [[ -z "${pat}" ]]; then
  echo "No PAT provided." >&2
  exit 1
fi

if [[ -z "${cached_pat}" ]]; then
  printf 'url=%s\nusername=%s\npassword=%s\n\n' "${remote_url}" "x-access-token" "${pat}" | git credential approve
fi

git push "${remote_url}" "${branch}"
