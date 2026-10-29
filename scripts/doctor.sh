#!/bin/bash
# 使い方: doctor.sh [shot|mov]   (既定 shot)
#   skill を動かす前に依存を確かめる。必須が欠けていれば exit 1 (直し方を表示する)。
MODE="${1:-shot}"
NG=0
ok()   { printf '  OK    %s\n' "$*"; }
ng()   { printf '  NG    %s\n' "$*"; NG=1; }
warn() { printf '  WARN  %s\n' "$*"; }

echo "ego-e2e-kit doctor ($MODE)"

# ego-browser: CLI と、その使い方ガイド (ego-browser skill) の両方が要る
if command -v ego-browser >/dev/null 2>&1; then
  if ego-browser skill 2>/dev/null | grep -q 'end of guide'; then
    ok "ego-browser ($(command -v ego-browser))"
  else
    ng "ego-browser はあるが 'ego-browser skill' が動かない -> ego-browser upgrade"
  fi
else
  ng "ego-browser が無い -> ego lite をインストールする (README の「依存」を参照)"
fi

if [ "$MODE" = "mov" ]; then
  for t in ffmpeg ffprobe; do
    if command -v "$t" >/dev/null 2>&1; then ok "$t"; else ng "$t が無い -> brew install ffmpeg"; fi
  done

  PY="${EGO_E2E_PYTHON:-}"
  if [ -z "$PY" ]; then
    for c in python3 /usr/bin/python3; do
      if bash -c '"$1" -I -c pass; exit $?' _ "$c" >/dev/null 2>&1; then PY="$c"; break; fi
    done
  fi
  if [ -n "$PY" ] && "$PY" -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    ok "python3 ($PY)"
  else
    ng "python3.9 以上が無い (EGO_E2E_PYTHON で指定できる)"
  fi

  # 音声は任意。VOICEVOX -> macOS say -> 音声なし (字幕のみ) の順に落ちる
  URL="${EGO_E2E_VOICEVOX_URL:-http://127.0.0.1:50021}"
  if curl -s --max-time 2 "$URL/version" >/dev/null 2>&1; then
    ok "VOICEVOX ($URL)"
  else
    warn "VOICEVOX が応答しない ($URL)。起動: docker start voicevox  (初回: docker run -d --name voicevox --restart unless-stopped -p 127.0.0.1:50021:50021 voicevox/voicevox_engine:cpu-latest)"
    if command -v say >/dev/null 2>&1; then
      warn "  -> 代わりに macOS の say を使う"
    else
      warn "  -> 代わりに音声なし (字幕のみ) で作る"
    fi
  fi
fi

[ "$NG" = 0 ] && echo "ready" || echo "必須の依存が足りない。上の NG を直してからやり直す"
exit "$NG"
