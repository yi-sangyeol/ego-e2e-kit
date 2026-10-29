"""ego-e2e-kit の設定を読む。

  config.py show                 プロジェクト設定と個人設定をまとめて表示する (足りない項目も出す)
  config.py resolve <作業ディレクトリ>  scenario.json と合わせて検証し、<作業ディレクトリ>/effective.json を書く

優先順位 (後ろが勝つ): 既定値 < 個人設定 < プロジェクト設定 < scenario.json
  個人設定:       $EGO_E2E_USER_CONFIG か ~/.config/ego-e2e-kit/config.json
  プロジェクト設定: $EGO_E2E_CONFIG か、カレントから上へ探した最初の .claude/ego-e2e.json
"""
import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "targets": {},
    "preconditions": [],
    "notes": "",
    "reading": {"tokens": {}, "words": {}},
    "voice": {
        "engine": "auto",  # auto | voicevox | say | none
        "voicevoxUrl": "http://127.0.0.1:50021",
        "speaker": 8,  # VOICEVOX の話者 ID。8 = 春日部つむぎ、3 = ずんだもん。一覧は GET /speakers
        "speed": 1.2,  # VOICEVOX の話速。1.5 を超えると音素が潰れて聞き取りにくい
        "pause": 0.5,  # 句読点の間の倍率
        "tempo": 1.4,  # 合成後の時間伸縮 (ffmpeg atempo)。speed 1.2 × tempo 1.4 で聞き取れる
        "sayVoice": "Kyoko",  # macOS say の声。一覧は say -v '?'
        "sayRate": 190,
        "credit": True,  # VOICEVOX のクレジット (例: VOICEVOX:春日部つむぎ) を動画に入れる
    },
    "video": {
        "speed": 1,  # 動画全体の倍速 (映像・音声・字幕トラック)
        "viewport": {"width": 1280, "height": 800},
        "taskSpace": "ego-e2e-kit",
    },
    "screenshots": "none",  # none | per-step | on-fail  (動画とは別に PNG を残すか)
}
SCREENSHOT_MODES = {"none", "per-step", "on-fail"}
ENGINES = {"auto", "voicevox", "say", "none"}


def merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"設定ファイルの JSON が壊れている: {path}: {e}")


def user_config_path():
    p = os.environ.get("EGO_E2E_USER_CONFIG")
    return Path(p) if p else Path.home() / ".config" / "ego-e2e-kit" / "config.json"


def project_config_path():
    p = os.environ.get("EGO_E2E_CONFIG")
    if p:
        return Path(p)
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / ".claude" / "ego-e2e.json").is_file():
            return d / ".claude" / "ego-e2e.json"
    return None


def base_config():
    cfg, sources = DEFAULTS, []
    for p in (user_config_path(), project_config_path()):
        if p and p.is_file():
            cfg = merge(cfg, load(p))
            sources.append(str(p))
    return cfg, sources


def check(cfg):
    errs = []
    if cfg["voice"]["engine"] not in ENGINES:
        errs.append(f"voice.engine は {sorted(ENGINES)} のどれか: {cfg['voice']['engine']}")
    if cfg["screenshots"] not in SCREENSHOT_MODES:
        errs.append(f"screenshots は {sorted(SCREENSHOT_MODES)} のどれか: {cfg['screenshots']}")
    if float(cfg["video"]["speed"]) <= 0:
        errs.append("video.speed は正の数")
    return errs


def show():
    cfg, sources = base_config()
    missing = []
    if not cfg["targets"]:
        missing.append("targets (テスト対象の URL / ポート)")
    if not cfg["preconditions"]:
        missing.append("preconditions (テストの前提: ログイン状態・データなど)")
    print(json.dumps({"sources": sources, "config": cfg, "missing": missing, "errors": check(cfg)},
                     ensure_ascii=False, indent=1))


def resolve(out):
    sc_path = out / "scenario.json"
    if not sc_path.is_file():
        sys.exit(f"scenario.json が無い: {out}")
    sc = load(sc_path)
    cfg, sources = base_config()
    # scenario 側の上書き。旧形式の viewport / taskSpace もそのまま受ける
    over = {k: sc[k] for k in ("voice", "video", "screenshots", "reading") if k in sc}
    if "viewport" in sc:
        over.setdefault("video", {})["viewport"] = sc["viewport"]
    if "taskSpace" in sc:
        over.setdefault("video", {})["taskSpace"] = sc["taskSpace"]
    cfg = merge(cfg, over)

    errs = check(cfg)
    # 情報が足りないまま撮らない。どれも「ユーザーに聞いて埋める」項目
    if not sc.get("target"):
        errs.append('scenario.json に "target" (テスト対象の URL) が無い。ユーザーに聞いて埋める')
    if "preconditions" not in sc:
        errs.append('scenario.json に "preconditions" (前提条件の配列。無ければ ["なし"]) が無い。ユーザーに聞いて埋める')
    if not sc.get("title"):
        errs.append('scenario.json に "title" が無い')
    if not sc.get("steps"):
        errs.append('scenario.json に "steps" が無い')
    for i, s in enumerate(sc.get("steps", []), 1):
        if not s.get("say"):
            errs.append(f"steps[{i}] に say が無い")
    v = sc.get("verdict") or {}
    if not (v.get("pass") and v.get("fail")):
        errs.append('scenario.json に "verdict": {"pass", "fail"} が無い')
    if errs:
        sys.exit("scenario.json / 設定に問題がある:\n  - " + "\n  - ".join(errs))

    eff = {"sources": sources, **cfg, "target": sc["target"], "preconditions": sc["preconditions"]}
    (out / "effective.json").write_text(json.dumps(eff, ensure_ascii=False, indent=1))
    print(f"config ok: {', '.join(sources) or '既定値のみ'}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "show":
        show()
    elif len(sys.argv) >= 3 and sys.argv[1] == "get":  # 例: config.py get voice.voicevoxUrl
        v = base_config()[0]
        for k in sys.argv[2].split("."):
            v = v[k]
        print(v)
    elif len(sys.argv) >= 3 and sys.argv[1] == "resolve":
        resolve(Path(sys.argv[2]))
    else:
        sys.exit(__doc__)
