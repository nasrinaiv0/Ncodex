#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
printf '%s\n' 'Initializing reviewed, pinned upstream commits. No upstream code will be executed.'
git submodule sync --recursive
git submodule update --init --recursive --jobs 3
git submodule status
printf '%s\n' 'Review the upstream licenses and security notes before using any project.'
