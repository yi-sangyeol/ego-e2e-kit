# ego-e2e-kit

[ego-browser](https://lite.ego.app/)（ego lite）で Web アプリを実際に操作して確かめる、Claude Code のプラグインです。2 つの skill が入っています。

| skill | 呼び方 | やること |
| --- | --- | --- |
| `e2e-shot` | `/ego-e2e-kit:e2e-shot [確認したいこと]` | 変更した画面を実操作し、エッジケースを含む約 10 件をスクショつきで報告する |
| `test-mov` | `/ego-e2e-kit:test-mov [撮りたいケース]` | 1 ケース 1 本の動画を作る。字幕・音声ナレーション・見るべき箇所の赤枠・字幕トラックが入る |

どちらも、**対象の URL（ポート）・テストケース・前提条件** のどれかが足りなければ、実行前にユーザーへ質問します。データを変える操作や外部への送信は、実行前に確認を取ります。

> ego-browser の非公式ツールです。ego-browser の開発元とは関係ありません。

## 依存

| 依存 | 必須 | 用途 |
| --- | --- | --- |
| **ego-browser (ego lite)** の CLI と skill | 両方の skill で必須 | ブラウザの実操作。[lite.ego.app](https://lite.ego.app/) からインストールし、`ego-browser skill` が動き、Claude Code から `ego-browser` skill が使えること |
| ffmpeg / ffprobe | `test-mov` で必須 | 動画の組み立て。macOS: `brew install ffmpeg` |
| Python 3.9+ | `test-mov` で必須 | 音声と動画の組み立て（標準ライブラリのみ） |
| VOICEVOX Engine | 任意 | 音声。無ければ macOS の `say`、それも無ければ音声なし（字幕のみ） |

ego-browser は Claude Code のプラグインではないため、プラグインの `dependencies` には書けません。各 skill は最初に `scripts/doctor.sh` で依存を確かめ、足りなければ直し方を出して止まります。手で確かめるときは次を実行します。

```bash
bash scripts/doctor.sh mov
```

VOICEVOX はローカルの Docker で動かすのが手軽です。

```bash
docker run -d --name voicevox --restart unless-stopped -p 127.0.0.1:50021:50021 voicevox/voicevox_engine:cpu-latest
```

## インストール

Claude Code の中で実行します。

```
/plugin marketplace add yi-sangyeol/ego-e2e-kit
/plugin install ego-e2e-kit@ego-e2e-kit
```

チームのリポジトリで候補に出したいときは、そのリポジトリの `.claude/settings.json` に次を書きます。メンバーはフォルダを信頼すると、インストールを勧められます。

```json
{
  "extraKnownMarketplaces": {
    "ego-e2e-kit": { "source": { "source": "github", "repo": "yi-sangyeol/ego-e2e-kit" } }
  },
  "enabledPlugins": { "ego-e2e-kit@ego-e2e-kit": true }
}
```

## 設定

設定は 2 か所に置けます。後ろのものが前のものを上書きします。

**既定値 < 個人設定 < プロジェクト設定 < scenario.json**

| 置き場所 | 向いている内容 |
| --- | --- |
| 個人: `~/.config/ego-e2e-kit/config.json`（`EGO_E2E_USER_CONFIG` で変更可） | 声・倍速・画面サイズ・スクショの有無など、好みのもの |
| プロジェクト: `<repo>/.claude/ego-e2e.json`（`EGO_E2E_CONFIG` で変更可。カレントから上へ探す） | 対象の URL・前提条件・プロジェクト固有の注意。チームでコミットして共有する |

雛形は [`templates/ego-e2e.json`](templates/ego-e2e.json) です。今の設定は次で確かめられます。

```bash
python3 scripts/config.py show
```

| キー | 既定値 | 意味 |
| --- | --- | --- |
| `targets` | `{}` | テスト対象の名前と URL（例: `{"admin": "http://localhost:3041"}`） |
| `preconditions` | `[]` | テストの前提（ログイン状態・データなど） |
| `notes` | `""` | プロジェクト固有の注意。skill が毎回読む |
| `reading` | `{}` | 読み上げ用の英語の読み（`tokens`: 完全一致、`words`: 小文字の単語） |
| `voice.engine` | `"auto"` | `auto`（VOICEVOX → say → なし）/ `voicevox` / `say` / `none` |
| `voice.speaker` | `8` | VOICEVOX の話者 ID。8 = 春日部つむぎ、3 = ずんだもん。一覧は `curl localhost:50021/speakers` |
| `voice.speed` / `voice.pause` / `voice.tempo` | `1.2` / `0.5` / `1.4` | VOICEVOX の話速、句読点の間の倍率、合成後の時間伸縮 |
| `voice.sayVoice` / `voice.sayRate` | `"Kyoko"` / `190` | macOS `say` の声と速さ（一覧は `say -v '?'`） |
| `voice.voicevoxUrl` | `"http://127.0.0.1:50021"` | VOICEVOX Engine の URL |
| `voice.credit` | `true` | VOICEVOX のクレジットを動画に入れる |
| `video.speed` | `1` | 動画全体の倍速（映像・音声・字幕トラック） |
| `video.viewport` | `1280×800` | 録画時の画面サイズ |
| `video.taskSpace` | `"ego-e2e-kit"` | ego-browser の TaskSpace 名。並列で撮るときはケースごとに分ける |
| `screenshots` | `"none"` | 動画とは別に PNG を残すか。`none` / `per-step` / `on-fail` |

例: ずんだもんの声で、2 倍速、ステップごとにスクショを残す個人設定。

```json
{ "voice": { "speaker": 3 }, "video": { "speed": 2 }, "screenshots": "per-step" }
```

例: VOICEVOX を使わず macOS の声にする。

```json
{ "voice": { "engine": "say", "sayVoice": "Kyoko" } }
```

## VOICEVOX のクレジット

VOICEVOX の音声は、キャラクターごとの利用規約でクレジット表記（例: `VOICEVOX:春日部つむぎ`）が求められます。`test-mov` は VOICEVOX を使ったとき、結論の字幕・字幕トラック・mp4 の comment にクレジットを自動で入れます。動画を外に出すときは消さないでください。話者ごとの規約は [VOICEVOX の公式サイト](https://voicevox.hiroshiba.jp/) で確かめてください。

## 開発

```bash
claude plugin validate . --strict
```

ローカルの checkout をそのまま試すときは `/plugin marketplace add /path/to/ego-e2e-kit` で追加します。

## ライセンス

MIT
