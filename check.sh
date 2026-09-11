#!/bin/bash
# config.yaml を編集したあと、push する前に動作確認するためのローカル用スクリプト。
#   1. config.yaml が読み込めるか（全角スペースやインデントの崩れを検出）
#   2. fetcher.py --dry-run で実際に取得してみる（papers.db・docs/ は変更しない）
#
# 毎日の「取得 → サイト生成 → push」は GitHub Actions が行うので、
# このスクリプトは commit / push を一切しない。
#
# 使い方:
#   ./check.sh           # 読み込み確認 + 試し取得（全誌に問い合わせるので少し時間がかかる）
#   ./check.sh --quick   # 読み込み確認だけ
set -euo pipefail

cd "$(dirname "$0")"

PYTHON=".venv/bin/python"

"$PYTHON" -c "import pathlib, fetcher; fetcher.load_config(pathlib.Path('config.yaml'))"
echo "config.yaml: 読み込み OK"

if [[ "${1:-}" != "--quick" ]]; then
  "$PYTHON" fetcher.py --dry-run
fi
