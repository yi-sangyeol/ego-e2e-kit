# ego-e2e-kit

[ego-browser](https://lite.ego.app/)（ego lite）で Web アプリを実際に操作して確かめる、Claude Code のプラグインです。2 つの skill が入っています。

| skill | 呼び方 | やること |
| --- | --- | --- |
| `e2e-shot` | `/ego-e2e-kit:e2e-shot [確認したいこと]` | 変更した画面を実操作し、エッジケースを含む約 10 件をスクショつきで報告する |
| `test-mov` | `/ego-e2e-kit:test-mov [撮りたいケース]` | 1 ケース 1 本の動画を作る。字幕・音声ナレーション・見るべき箇所の赤枠・字幕トラックが入る |

どちらも、**対象の URL（ポート）・テストケース・前提条件** のどれかが足りなければ、実行前にユーザーへ質問します。データを変える操作や外部への送信は、実行前に確認を取ります。

> ego-browser の非公式ツールです。ego-browser の開発元とは関係ありません。

## セットアップ

上から順に進めてください。**1 と 2 は両方の skill で必須**です。3 は `test-mov` で音声を入れるときに必要です。

| # | やること | 必要な skill | 無いとどうなるか |
| --- | --- | --- | --- |
| 1 | ego lite と ego-browser skill を入れる | 両方 | 動かない（`doctor.sh` が止める） |
| 2 | ffmpeg と Python 3.9 以上を入れる | `test-mov` | 動画を作れない |
| 3 | Docker を入れ、VOICEVOX Engine を起動する | `test-mov`（任意） | macOS の `say` の声になる。macOS 以外は音声なし（字幕のみ） |
| 4 | このプラグインを入れる | 両方 | — |
| 5 | 依存を確かめる | 両方 | — |

### 1. ego lite と ego-browser skill を入れる（必須）

ブラウザの操作は、すべて ego lite（ego-browser）でします。**アプリ本体の CLI と、Claude Code 用の `ego-browser` skill の両方**が要ります。

1. [lite.ego.app](https://lite.ego.app/) から ego lite をダウンロードして入れる。
2. ego lite を起動し、**初回のオンボーディングを最後まで済ませる**。ここで次の 2 つが入ります。
   - CLI: `~/.local/bin/ego-browser`
   - skill: `~/.claude/skills/ego-browser`（ego lite のアプリ内のファイルへの symlink）
3. 入ったか確かめる。

   ```bash
   ego-browser skill | tail -n 1     # "[ego-browser:skill] end of guide" で終われば OK
   ls -l ~/.claude/skills/ego-browser
   ```

   `ego-browser: command not found` になるときは、`~/.local/bin` を `PATH` に足してください。

> ego-browser の skill は、Claude Code のプラグインとしては配られていません。そのため、このプラグインの依存（`dependencies`）として自動では入りません。必ず手で入れてください。

### 2. ffmpeg と Python を入れる（`test-mov` で必須）

```bash
brew install ffmpeg          # ffmpeg と ffprobe が入る
python3 --version            # 3.9 以上（macOS 標準の /usr/bin/python3 でよい）
```

Python は標準ライブラリだけを使います。`pip install` は要りません。`python3` が落ちる環境（pyenv のシムなど）では、自動で `/usr/bin/python3` を使います。明示するときは `EGO_E2E_PYTHON=/path/to/python3` を設定します。

### 3. Docker と VOICEVOX Engine（`test-mov` の音声。任意）

ナレーションの声は [VOICEVOX](https://voicevox.hiroshiba.jp/) Engine で作ります。**Docker の環境が必要で、撮影のたびに VOICEVOX Engine が起動している必要があります。**

1. Docker を入れる（[Docker Desktop](https://www.docker.com/products/docker-desktop/) か [OrbStack](https://orbstack.dev/) など）。起動して `docker version` が通ることを確かめる。
2. 初回だけ、VOICEVOX Engine のコンテナを作って起動する。

   ```bash
   docker run -d --name voicevox --restart unless-stopped \
     -p 127.0.0.1:50021:50021 voicevox/voicevox_engine:cpu-latest
   ```

3. 2 回目以降は、止まっていれば起動する（`--restart unless-stopped` なので、Docker が動いていれば通常は自動で上がります）。

   ```bash
   docker start voicevox
   ```

4. 応答を確かめる。

   ```bash
   curl -s localhost:50021/version          # バージョンが返れば OK
   curl -s localhost:50021/speakers | head  # 話者の一覧（声を選ぶときの ID）
   ```

VOICEVOX が応答しないときは、macOS では `say`（既定は Kyoko）の声に自動で切り替わります。macOS 以外では音声なし（字幕のみ）になります。最初から VOICEVOX を使わないなら、設定で `"voice": {"engine": "say"}` か `"none"` にします（[設定](#設定)）。

### 4. プラグインを入れる

**Claude Code の中**（プロンプト欄）で、次の 2 行を順に実行します。

```
/plugin marketplace add yi-sangyeol/ego-e2e-kit
/plugin install ego-e2e-kit@ego-e2e-kit
```

- 1 行目で、この GitHub リポジトリを marketplace として登録します。
- 2 行目で、プラグインを入れます。`ego-e2e-kit@ego-e2e-kit` は「プラグイン名@marketplace 名」です。
- 入れた後は Claude Code を再起動します。

ターミナルからなら次のとおりです。

```bash
claude plugin marketplace add yi-sangyeol/ego-e2e-kit
claude plugin install ego-e2e-kit@ego-e2e-kit
```

入ったかは、`/plugin` の一覧に `ego-e2e-kit` があるか、プロンプト欄で `/ego-e2e-kit:` と打って `e2e-shot` と `test-mov` が候補に出るかで確かめます。

| 操作 | ターミナル |
| --- | --- |
| 入っているか確かめる | `claude plugin list` |
| 更新 | `claude plugin marketplace update ego-e2e-kit` → `claude plugin update ego-e2e-kit@ego-e2e-kit` |
| 削除 | `claude plugin uninstall ego-e2e-kit@ego-e2e-kit` |

#### チームのリポジトリで勧める

チームのリポジトリの `.claude/settings.json` に次を書いてコミットします。メンバーがそのフォルダを信頼すると、marketplace の登録とインストールを勧められます。1〜3 の依存は、各自が入れる必要があります。

```json
{
  "extraKnownMarketplaces": {
    "ego-e2e-kit": { "source": { "source": "github", "repo": "yi-sangyeol/ego-e2e-kit" } }
  },
  "enabledPlugins": { "ego-e2e-kit@ego-e2e-kit": true }
}
```

### 5. 依存を確かめる

skill は実行のたびに最初に依存を確かめ、足りなければ直し方を出して止まります。手で確かめるときは、このリポジトリを clone して次を実行します。

```bash
bash scripts/doctor.sh mov   # test-mov 用（ego-browser・ffmpeg・python3・VOICEVOX）
bash scripts/doctor.sh shot  # e2e-shot 用（ego-browser だけ）
```

`ready` と出れば準備完了です。`NG` は必須の依存が欠けています。`WARN` は任意の依存（VOICEVOX）が無いという意味で、そのまま使えます。

## 使い方

テストしたいプロジェクトのディレクトリで Claude Code を開き、次のように呼びます。

```
/ego-e2e-kit:e2e-shot ログイン画面のバリデーションを確認して
/ego-e2e-kit:test-mov #4 変更期限 ケースA
```

対象の URL・前提条件をプロジェクト設定（`.claude/ego-e2e.json`）に書いておくと、毎回聞かれずに済みます。書いていなければ、skill が実行前に質問します。

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
