#!/bin/bash
# 使い方: make.sh <作業ディレクトリ> <出力名>.mp4 [--speed N] [--data <キャッシュの置き場所>]
#   作業ディレクトリに scenario.json を置いておく。設定 -> 音声 -> 録画 -> 組み立て -> 検証 までを 1 回で通す。
#   プロジェクト設定 (.claude/ego-e2e.json) はカレントから上へ探すので、テスト対象のプロジェクトで実行する。
# 終了コード: 0 合格 / 1,2 実行の失敗 / 3 赤枠の対象が見つからない / 4 動画はできたが expect が外れた
set -euo pipefail
[ $# -ge 2 ] || { sed -n '2,5p' "$0" >&2; exit 1; }
O="$(cd "$1" && pwd)"; DEST="$2"; shift 2
SPEED=""; DATA="${EGO_E2E_DATA:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --speed) SPEED="$2"; shift 2 ;;
    --data) DATA="$2"; shift 2 ;;
    *) echo "不明な引数: $1" >&2; exit 1 ;;
  esac
done
DATA="${DATA:-$HOME/.cache/ego-e2e-kit}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"

# 動く python3 を選ぶ (pyenv のシムが落ちる環境があるので、実際に起動できるかで判定する)
PY="${EGO_E2E_PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3 /usr/bin/python3; do
    if bash -c '"$1" -I -c pass; exit $?' _ "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "動く python3 が見つからない (EGO_E2E_PYTHON で指定できる)" >&2; exit 1; }

"$PY" -I "$ROOT/scripts/config.py" resolve "$O"
[ -n "$SPEED" ] || SPEED="$("$PY" -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["video"]["speed"])' "$O/effective.json")"

"$PY" -I "$HERE/build.py" tts "$O" "$DATA/voice-cache"

# run.mjs は先頭に作業ディレクトリを埋めて ego-browser に渡す (stdin 実行では import できない前提)
RUNLOG="$O/run.log"
{ printf 'const OUT = %s;\n' "$("$PY" -I -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$O")"; cat "$HERE/run.mjs"; } | ego-browser nodejs > "$RUNLOG" 2>&1 || true
RESULT="$(grep '^{' "$RUNLOG" | tail -n 1 || true)"
# 例外で落ちたときは JSON が出ない。原因が分かるよう run.log の末尾を必ず出す
[ -n "$RESULT" ] || { echo "run.mjs の結果 JSON が取れなかった。run.log の末尾:" >&2; tail -n 30 "$RUNLOG" >&2; exit 2; }
echo "$RESULT"

# 赤枠の対象が見つからなかったら、組み立てる前に落とす (撮り直しが必要)
if echo "$RESULT" | "$PY" -I -c 'import json,sys;sys.exit(0 if not json.loads(sys.stdin.read())["missing"] else 1)'; then :; else
  echo "赤枠の対象が見つからないステップがある (result.json の found を確認して mark を直す)" >&2; exit 3
fi

"$PY" -I "$HERE/build.py" build "$O" "$DEST" "$SPEED"

# expect が外れていれば、動画は作るが非ゼロで終わる (不合格ナレーションが入っている)
echo "$RESULT" | "$PY" -I -c 'import json,sys;r=json.loads(sys.stdin.read());sys.exit(0 if r["verdict"]=="pass" else 4)'
