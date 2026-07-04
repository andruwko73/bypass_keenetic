#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

branch=${1:-main}

echo "Fetching origin..."
git fetch origin

echo "Checking out $branch..."
git checkout "$branch"

echo "Merging origin/$branch..."
git merge --ff-only "origin/$branch"

echo "Pushing $branch to userfork..."
git push userfork "$branch"

echo "Update complete: userfork/$branch is now synced with origin/$branch."