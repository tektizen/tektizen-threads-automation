#!/usr/bin/env bash
# Commit changed data/prompts and push, rebasing onto concurrent commits.
# Concurrent JSON edits are merged record-by-record by the tektizen-json merge driver.
set -euo pipefail

message="${1:?commit message required}"
branch="${GITHUB_REF_NAME:-main}"

git config user.name "tektizen-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git add data config agents/prompts
if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi
# [CF-Pages-Skip]: data commits don't need a dashboard rebuild (it reads data live).
git commit --quiet -m "${message} [CF-Pages-Skip]"

for attempt in 1 2 3 4 5; do
  if git push --quiet origin "HEAD:${branch}"; then
    echo "Pushed on attempt ${attempt}."
    exit 0
  fi
  echo "Push rejected (attempt ${attempt}); rebasing onto the latest ${branch}..."
  if ! git pull --rebase --quiet origin "${branch}"; then
    git rebase --abort || true
    echo "::error::Could not merge data changes with concurrent updates."
    exit 1
  fi
  sleep $((attempt * 2))
done
echo "::error::Push failed after 5 attempts."
exit 1
