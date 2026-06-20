#!/bin/bash
# 毎日1回実行する想定のスクリプト:
#   1. 論文を取得して DB に保存
#   2. 静的サイト(docs/index.html)を生成
#   3. 変更を GitHub に push → GitHub Pages に反映
#
# cron 登録例（毎朝8時）:
#   0 8 * * * /Users/asadasoichiro/claudeworks/paper_fetcher/daily.sh >> /Users/asadasoichiro/claudeworks/paper_fetcher/cron.log 2>&1
set -euo pipefail

cd "$(dirname "$0")"

PYTHON=".venv/bin/python"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') daily run ====="

# 1. 取得
"$PYTHON" fetcher.py

# 2. 静的サイト生成
"$PYTHON" build_site.py

# 3. 変更があればコミット（リモートが設定済みなら push）
if [[ -n "$(git status --porcelain docs/)" ]]; then
  git add docs/
  git commit -m "Update papers $(date '+%Y-%m-%d')"
  if git remote get-url origin >/dev/null 2>&1; then
    git push && echo "push 完了"
  else
    echo "コミット完了（GitHub リモート未設定のため push はスキップ）"
  fi
else
  echo "新規論文なし（コミットなし）"
fi
