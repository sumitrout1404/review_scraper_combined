#!/usr/bin/env bash
# Commit (if there are changes) and push to all three repositories:
#   origin   -> review_scraper_combined  (this repo, backend/ + frontend/)
#   backend  -> review_scraper_backend   (contents of backend/ at the root)
#   frontend -> review_scraper_frontend  (contents of frontend/ at the root)
#
# Usage: ./scripts/push-all.sh "commit message"
set -euo pipefail

cd "$(dirname "$0")/.."

MESSAGE="${1:-}"
if [[ -n "$(git status --porcelain)" ]]; then
    if [[ -z "$MESSAGE" ]]; then
        echo "There are uncommitted changes. Pass a commit message:" >&2
        echo "  ./scripts/push-all.sh \"your message\"" >&2
        exit 1
    fi
    git add -A
    git commit -m "$MESSAGE"
fi

for remote in origin backend frontend; do
    git remote get-url "$remote" >/dev/null 2>&1 || {
        echo "Missing remote '$remote'. See README section 0." >&2
        exit 1
    }
done

echo "==> combined"
git push origin main

echo "==> backend"
git subtree push --prefix=backend backend main

echo "==> frontend"
git subtree push --prefix=frontend frontend main

echo "Done — all three repositories updated."
