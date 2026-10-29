"""test-mov の音声作成・動画組み立て。設定は make.sh が書いた <作業ディレクトリ>/effective.json から読む。

  build.py tts   <作業ディレクトリ> <キャッシュ>           scenario.json の文を並列で音声化 -> narration.json, voice.json
  build.py build <作業ディレクトリ> <出力名>.mp4 [速度]    timeline.json から mp4 とコンタクトシート (sheet.png) を作る
"""
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FF = shutil.which("ffmpeg") or sys.exit("ffmpeg が見つからない (macOS: brew install ffmpeg)")
FP = shutil.which("ffprobe") or sys.exit("ffprobe が見つからない (ffmpeg に同梱)")
HOLD_PAD = 0.4  # ナレーションの後ろに残す余白 (秒)


def duration(path):
    out = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


KANJI = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNIT = {"十": 10, "百": 100, "千": 1000}
# 読みは漢数字のほうが正しい (三日 = みっか) ので、音声は原文のまま、字幕だけ半角のアラビア数字にする
COUNTER = r"(?:日前|日後|日間|日|か月|ヶ月|ヵ月|カ月|月|年|時間|時|分|秒|円|件|名|人|泊|室|回|歳|週間|週|個|枚|割|階|番目|パーセント|%)"
NUM = re.compile(rf"([〇零一二三四五六七八九十百千万]+)(?={COUNTER})")


def kanji_to_int(k):
    total, cur, sect = 0, 0, 0
    for ch in k:
        if ch in KANJI:
            cur = cur * 10 + KANJI[ch] if (cur and sect == 0 and k.count("十百千万") == 0) else KANJI[ch]
        elif ch in UNIT:
            sect += (cur or 1) * UNIT[ch]
            cur = 0
        elif ch == "万":
            total += (sect + cur or 1) * 10000
            sect = cur = 0
    return total + sect + cur


def disp(text):
    def conv(m):
        k = m.group(1)
        # 「十分な」(= 足りている) は 10 分ではない
        if k == "十" and text[m.end():m.end() + 2] in ("分な", "分に", "分で", "分だ", "分、", "分。"):
            return k
        n = kanji_to_int(k)
        return f"{n:,}" if n >= 1000 else str(n)
    out = NUM.sub(conv, text)
    return out.translate(str.maketrans("０１２３４５６７８９％", "0123456789%"))


LETTERS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "エー ビー シー ディー イー エフ ジー エイチ アイ ジェー ケー エル エム エヌ オー ピー キュー アール エス ティー ユー ブイ ダブリュー エックス ワイ ゼット".split()))
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[_.\-][A-Za-z0-9]+)*")
SPLIT = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")  # camelCase / ACRONYM / 数字の境


def load_reading(*extras):
    d = json.loads((Path(__file__).parent / "reading.json").read_text(encoding="utf-8"))
    tokens, words = dict(d["tokens"]), dict(d["words"])
    for e in extras:  # プロジェクト設定 -> scenario.json の順に足す
        tokens |= e.get("tokens", {})
        words |= e.get("words", {})
    return tokens, {k.lower(): v for k, v in words.items()}


def read_part(part, words, unknown):
    if part.isdigit():
        return part
    if part.lower() in words:
        return words[part.lower()]
    if part.isupper() and len(part) <= 5:  # 辞書にない略語は 1 文字ずつ読む (SQL -> エスキューエル)
        return "".join(LETTERS[c] for c in part)
    unknown.add(part)
    return part


def to_reading(text, tokens, words, unknown):
    """英語のトークンをカタカナにする。読み上げ専用で、字幕には使わない"""
    def conv(m):
        tok = m.group(0)
        if tok in tokens:
            return tokens[tok]
        out = []
        for seg in re.split(r"([_.\-])", tok):
            if seg in "_-":
                continue
            if seg == ".":
                out.append("ドット")
                continue
            out += [read_part(x, words, unknown) for x in SPLIT.findall(seg)]
        return "".join(out)
    return TOKEN.sub(conv, text)


class Voice:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = cfg["voicevoxUrl"].rstrip("/")

    def voicevox_up(self):
        try:
            urllib.request.urlopen(f"{self.url}/version", timeout=2).read()
            return True
        except Exception:
            return False

    def pick(self):
        want = self.cfg["engine"]
        has_say = platform.system() == "Darwin" and shutil.which("say")
        if want == "voicevox":
            if self.voicevox_up():
                return "voicevox"
            sys.exit(f"voice.engine=voicevox だが VOICEVOX が応答しない: {self.url} (docker start voicevox)")
        if want == "say":
            return "say" if has_say else sys.exit("voice.engine=say は macOS でのみ使える")
        if want == "none":
            return "none"
        if self.voicevox_up():
            return "voicevox"
        print(f"VOICEVOX が応答しない ({self.url}) ので {'macOS の say' if has_say else '音声なし (字幕のみ)'} で作る",
              file=sys.stderr)
        return "say" if has_say else "none"

    def speaker_name(self):
        try:
            for sp in json.loads(urllib.request.urlopen(f"{self.url}/speakers", timeout=5).read()):
                for st in sp["styles"]:
                    if st["id"] == self.cfg["speaker"]:
                        return sp["name"] if st["name"] == "ノーマル" else f"{sp['name']}（{st['name']}）"
        except Exception:
            pass
        return f"speaker {self.cfg['speaker']}"

    def voicevox_wav(self, text):
        sp = self.cfg["speaker"]
        q = urllib.request.urlopen(urllib.request.Request(
            f"{self.url}/audio_query?speaker={sp}&text={urllib.parse.quote(text)}", method="POST"), timeout=60).read()
        query = json.loads(q)
        query.update(speedScale=self.cfg["speed"], pauseLengthScale=self.cfg["pause"], postPhonemeLength=0.1)
        return urllib.request.urlopen(urllib.request.Request(
            f"{self.url}/synthesis?speaker={sp}", data=json.dumps(query).encode(),
            headers={"Content-Type": "application/json"}, method="POST"), timeout=120).read()

    def tag(self, engine):
        c = self.cfg
        if engine == "voicevox":
            return f"vv{c['speaker']}|{c['speed']}|{c['pause']}|{c['tempo']}"
        if engine == "say":
            return f"say|{c['sayVoice']}|{c['sayRate']}"
        return "none"

    def speak(self, engine, cache, text, spoken):
        key = hashlib.sha1(f"{self.tag(engine)}|{spoken}".encode()).hexdigest()[:16]
        f = cache / f"{key}.{'aiff' if engine == 'say' else 'wav'}"
        if not f.exists():
            tmp = f.with_name(f.stem + ".tmp" + f.suffix)
            if engine == "voicevox":
                raw = f.with_name(f.stem + ".raw" + f.suffix)
                raw.write_bytes(self.voicevox_wav(spoken))
                tempo = float(self.cfg["tempo"])
                if tempo != 1.0:
                    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(raw), "-filter:a", f"atempo={tempo}", str(tmp)], check=True)
                    raw.unlink()
                else:
                    raw.rename(tmp)
            elif engine == "say":
                subprocess.run(["say", "-v", self.cfg["sayVoice"], "-r", str(self.cfg["sayRate"]), "-o", str(tmp), spoken], check=True)
            else:  # 音声なし: 字幕を読める長さの無音 (1 文字 0.13 秒、最短 2 秒)
                sec = max(2.0, len(text) * 0.13)
                subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                                "-t", f"{sec:.2f}", str(tmp)], check=True)
            tmp.rename(f)
        return text, {"file": str(f), "sec": duration(f), "disp": disp(text), "read": spoken}


def tts(out, cache):
    sc = json.loads((out / "scenario.json").read_text())
    eff = json.loads((out / "effective.json").read_text())
    texts = [s["say"] for s in sc["steps"]] + [sc["verdict"]["pass"], sc["verdict"]["fail"]]
    cache.mkdir(parents=True, exist_ok=True)
    voice = Voice(eff["voice"])
    engine = voice.pick()
    tokens, words = load_reading(eff.get("reading", {}))
    unknown = set()
    spoken = {t: to_reading(t, tokens, words, unknown) if engine != "none" else t for t in dict.fromkeys(texts)}
    with ThreadPoolExecutor(max_workers=4) as ex:
        table = dict(ex.map(lambda t: voice.speak(engine, cache, t, spoken[t]), spoken))
    if unknown:
        print(f"読みが分からない英語 (そのまま読むと崩れる): {sorted(unknown)} -> 設定か scenario.json の reading.words に足す",
              file=sys.stderr)
    credit = f"VOICEVOX:{voice.speaker_name()}" if engine == "voicevox" and eff["voice"]["credit"] else ""
    (out / "narration.json").write_text(json.dumps(table, ensure_ascii=False, indent=1))
    (out / "voice.json").write_text(json.dumps({"engine": engine, "credit": credit}, ensure_ascii=False))
    print(f"tts ok: {len(table)} 文 ({engine}{', ' + credit if credit else ''})")


def srt_time(sec):
    ms = int(sec * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def encoders():
    # VideoToolbox (macOS のハードウェア) が使えれば使い、無ければ libx264
    names = subprocess.run([FF, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "h264_videotoolbox" in names:
        yield ["-c:v", "h264_videotoolbox", "-b:v", "8M"]
    yield ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def build(out, dest, speed):
    narr = json.loads((out / "narration.json").read_text())
    steps = json.loads((out / "timeline.json").read_text())["steps"]
    credit = json.loads((out / "voice.json").read_text()).get("credit", "")
    sp = lambda x: x / speed

    lines, srt, audios, sheet = [], [], [], []
    T = 0.0  # 出力側の現在時刻 (秒)
    for k, st in enumerate(steps):
        fr = st["frames"]
        T0 = T  # ナレーションはステップの開始と同時に始める（操作中も喋る）
        # 操作中のフレームは実時刻どおりに並べる (最後の 1 枚の手前まで)
        for i, f in enumerate(fr[:-1]):
            d = max(sp((fr[i + 1]["t"] - f["t"]) / 1000), 0.001)
            lines.append(f"file '{out / 'frames' / f['name']}'\nduration {d:.3f}")
            T += d
        # 最後の 1 枚は、ナレーションが終わるまで保持する。操作のほうが長ければ短い余白だけ
        hold = max(sp(st["sec"] + HOLD_PAD) - (T - T0), 0.3)
        last = fr[-1]
        lines.append(f"file '{out / 'frames' / last['name']}'\nduration {hold:.3f}")
        audios.append((narr[st["text"]]["file"], T0))
        text = narr[st["text"]]["disp"]
        if credit and k == len(steps) - 1:
            text += f"\n{credit}"
        srt.append(f"{k + 1}\n{srt_time(T0)} --> {srt_time(T + hold)}\n{text}\n")
        sheet.append(out / "frames" / last["name"])
        T += hold
    lines.append(f"file '{sheet[-1]}'")  # concat demuxer は最後の duration を無視するため
    (out / "frames.txt").write_text("\n".join(lines) + "\n")
    (out / "captions.srt").write_text("\n".join(srt))

    inputs, filters = [], []
    for i, (path, t) in enumerate(audios):
        inputs += ["-i", path]
        tempo = f"atempo={speed}," if speed != 1 else ""
        ms = int(t * 1000)
        filters.append(f"[{i + 2}:a]{tempo}adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(audios)))
    filters.append(f"{mix}amix=inputs={len(audios)}:normalize=0,apad[aout]")

    target = out / dest
    meta = ["-metadata", f"comment={credit}"] if credit else []
    for enc in encoders():
        r = subprocess.run([
            FF, "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(out / "frames.txt"),
            "-i", str(out / "captions.srt"), *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "0:v", "-map", "[aout]", "-map", "1:s",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=25", *enc, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-c:s", "mov_text", "-metadata:s:s:0", "language=jpn", *meta,
            "-t", f"{T:.3f}", str(target),
        ])
        if r.returncode == 0:
            break
    else:
        sys.exit("ffmpeg に失敗した")

    # コンタクトシート: 各ステップの最後の 1 枚を 1 回の ffmpeg で並べる (見るのはこの 1 枚だけでよい)
    cols = 2 if len(sheet) > 1 else 1
    rows = -(-len(sheet) // cols)
    lst = out / "sheet.txt"
    lst.write_text("\n".join(f"file '{p}'\nduration 1" for p in sheet) + "\n")
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"scale=720:-2,tile={cols}x{rows}", "-frames:v", "1", str(out / "sheet.png")], check=True)

    streams = subprocess.run([FP, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(target)],
                             capture_output=True, text=True).stdout.replace(",", " ").split()
    shots = sorted(str(p) for p in (out / "shots").glob("*.png")) if (out / "shots").is_dir() else []
    print(json.dumps({"video": str(target), "sheet": str(out / "sheet.png"), "shots": shots,
                      "seconds": round(duration(target), 1), "streams": streams}, ensure_ascii=False))
    if sorted(streams) != ["audio", "subtitle", "video"]:
        sys.exit(f"video/audio/subtitle の 3 ストリームが揃っていない: {streams}")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "tts":
        tts(Path(sys.argv[2]), Path(sys.argv[3]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "build":
        build(Path(sys.argv[2]), sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 1.0)
    else:
        sys.exit(__doc__)
