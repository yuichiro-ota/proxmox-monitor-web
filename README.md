# Proxmox Monitor

Proxmox VEのノード・VM・LXC・ストレージをリアルタイムで監視するWebダッシュボード。

## 構成

```
proxmox_monitor/
├── api/                 # バックエンド (FastAPI)
│   ├── Dockerfile
│   └── main.py          # Proxmox APIへの接続・データ収集・REST API
├── frontend/            # フロントエンド (Vue.js)
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
├── pyproject.toml       # Python依存関係の定義
├── uv.lock              # 依存関係のバージョン固定ファイル
├── docker-compose.yml
└── .env                 # 認証情報 (要作成)
```

**コンテナ構成**

| コンテナ | 役割 |
|---|---|
| `back` | FastAPI。リクエスト時にProxmox APIからライブデータを取得 |
| `front` | nginx。Vue.jsの静的ファイルを配信し `/api/` を `back` にプロキシ |

## セットアップ

### 1. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集：

```env
PROXMOX_HOST=192.168.1.10         # ProxmoxのIPまたはFQDN (https://不要) ※実際の値に変更
PROXMOX_USER=monitor@pve          # ユーザー (user@realm 形式)
PROXMOX_TOKEN_NAME=monitoring     # APIトークン名
PROXMOX_TOKEN_VALUE=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PROXMOX_VERIFY_SSL=false
```

パスワード認証を使う場合は `PROXMOX_TOKEN_NAME` / `PROXMOX_TOKEN_VALUE` の代わりに：

```env
PROXMOX_PASSWORD=yourpassword
```

### 2. 起動

```bash
docker compose up -d --build
```

ブラウザで `http://<サーバーIP>` にアクセス。

## 動作仕様

- ページを開いたとき・手動更新・10秒ごとの自動更新のたびに `/api/latest` を叩く（間隔は `frontend/src/App.vue` の `POLL_INTERVAL_SEC`）
- `back` コンテナがそのつどProxmox APIへ接続してライブデータを返す
- データはファイルに保存しない（ステートレス）

## 画面の見かた（フロントエンド）

ダッシュボードは **系統図（トポロジ）** と **詳細一覧** の2ビュー構成で、ヘッダーのタブ（`系統図` / `詳細一覧`）で切り替えます。上部には常にステータスバーと警告パネルが表示されます。

### 上部ステータスバー

6つのタイルで全体状況を集計表示します。数値は **「稼働数 / 総数」** の分数、各タイル左端のバーが **緑=正常 / 赤=異常** を示します。

| タイル | 数値 | 赤（異常）になる条件 |
|---|---|---|
| 起動ノード | 稼働中(ノード+オンプレ) / 監視対象総数 | ダウンが1件以上 |
| ダウン | ダウン数 / 監視対象総数 | ダウンが1件以上 |
| Proxmox | 稼働ノード / 全ノード | ダウンしたノードがある |
| オンプレ | 稼働ホスト / 全ホスト | ダウンしたホストがある |
| ネットワーク機器 | 台数（ルーター） | 常に緑（※後述） |
| VM / LXC | 稼働ゲスト / 全ゲスト | 「稼働→停止」に落ちたゲストがある |

> ネットワーク機器（ルーター）は死活監視に対応しない機器の場合、常に緑（静的表示）です。SNMP等で死活監視できる機器に変更する際は監視処理を実装してください（`frontend/src/topology.js`）。

### 系統図ビュー

`ルーター → ネットワークセグメント → グループ（Proxmoxクラスタ / オンプレサーバー）→ ノード → VM・LXC` の階層をツリー表示します。ウィンドウ幅に合わせて全体を自動スケール（横スクロールなし）。カードをクリックすると詳細モーダルが開きます。

### 詳細一覧ビュー

詳細カードを **種類別セクション**（`Proxmox` / `オンプレサーバー` / `VM / LXC`）に分けてグリッド表示します。中身は詳細モーダルと同一です。

## 警告（アラーム）の発生条件

警告パネルは重大度順に表示され、該当が無ければ「✅ すべて正常に稼働しています」を表示します。使用率のしきい値は `frontend/src/App.vue` の `CPU_WARN` / `MEM_WARN`（既定 **85%**）で変更できます。

| レベル | 対象 | 発生条件 | メッセージ例 |
|---|---|---|---|
| 🔴 重大 | Proxmoxノード | ノードがダウン（`online == false`） | Proxmoxノード「pve2」がダウンしています |
| 🔴 重大 | オンプレサーバー | ホストがダウン（`online == false`） | オンプレサーバー「Main PC」がダウンしています |
| ⚠️ 警告 | Proxmoxノード（稼働中） | CPU使用率 ≥ `CPU_WARN` | Proxmoxノード「pve1」CPU使用率が高い (91%) |
| ⚠️ 警告 | Proxmoxノード（稼働中） | メモリ使用率 ≥ `MEM_WARN` | Proxmoxノード「pve1」メモリ使用率が高い (91%) |
| ⚠️ 警告 | オンプレサーバー（稼働中） | CPU使用率 ≥ `CPU_WARN` | オンプレ「Main PC」CPU使用率が高い (88%) |
| ⚠️ 警告 | オンプレサーバー（稼働中） | メモリ使用率 ≥ `MEM_WARN` | オンプレ「Main PC」メモリ使用率が高い (88%) |
| ⚠️ 警告 | VM / LXC | 「ダウン」した場合のみ（下記） | ダウンしたVM/LXC: test-vm (1件) |

**VM/LXC の扱い（重要）**

- Proxmox の VM/LXC は **常時メモリ使用率が高い前提**のため、**CPU/メモリの高負荷は通知しません**。
- VM/LXC は **「ダウン」したときだけ**通知します。ここでの「ダウン」とは、
  **ページを開いてから一度でも稼働(running)を観測したゲストが、その後 running でなくなった**状態を指します
  （ページを開いた後に起動したVMが停止した場合も検知します）。
- 最初から停止していて一度も起動していないVM（意図的にオフのVM等）は通知対象外です。
- ダウンした VM/LXC は警告パネルに **重大（🔴）** として1件ずつ表示され、アバターも反応します。
- この判定基準（ベースライン）は**ブラウザのセッション単位**で保持され、ページを再読み込みするとその時点の状態が新しい基準になります。

## VRMアバター

系統図・詳細一覧の前面（右下）に VRM アバターを常時表示します。

- モデル: `frontend/public/avatar.vrm`（VRM 0.x）。描画は `three` + `@pixiv/three-vrm`。
- 通常はアイドル動作（呼吸・まばたき）。
- **ダウン（重大警告）が発生すると**、心配顔になり吹き出しに「**サーバー落ちました！**」／VM・LXCのみの停止なら「**VMが止まりました！**」＋対象名を表示します（高負荷など警告レベルでは吹き出しは出ません）。
  - 対象は Proxmox ノード・オンプレサーバーのダウンに加え、**VM/LXC の停止**も含みます。
- ※ 将来的にアバターのボイス再生を実装予定。

### アバターのセリフ生成（Ollama）

平常時（ダウンが無いとき）は、**Ollama** に現在の監視状況を渡して短い日本語コメントを生成し、吹き出しに定期表示します（既定: 45秒ごとに生成、30秒間表示）。生成の問い合わせ中は「**・・・**」の吹き出し（ドットのアニメーション）を出して考え中であることを示します。ダウン発生時はアラートが最優先されます。

処理経路は `フロント → バックエンド /api/avatar/say → Ollama` です（ブラウザから直接叩かないので CORS 不要、接続先はサーバー側の環境変数で一元管理）。

接続先は `.env` で設定します（**後から別PCのIPに変更するときはここを書き換えるだけ**）:

```env
OLLAMA_URL=http://<OllamaのPCのIP>:11434   # Ollama が動くPCのIP:ポート
OLLAMA_MODEL=<pull済みモデル名>             # 例: llama3.2 / gemma3 / qwen2.5
```

（両方設定したときのみ有効。未設定ならセリフ機能はオフで、監視には影響しません）

**Ollama 側の準備（重要）**

- 監視スタックとは別ホストの Ollama を使う場合、Ollama を **全インターフェースで待ち受け**させる必要があります。
  - Windows: 環境変数 `OLLAMA_HOST=0.0.0.0` を設定して Ollama を再起動。
  - ファイアウォールで **11434/TCP のインバウンドを許可**（windows_exporter の 9182 と同様）:
    ```powershell
    New-NetFirewallRule -DisplayName "ollama 11434" -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow -Profile Any
    ```
- 使うモデルを事前に pull しておく: `ollama pull llama3.2`
- 未設定・未起動でも致命的にはならず、その場合は吹き出しのセリフが出ないだけです（監視機能には影響しません）。

生成間隔・表示時間はフロントの `frontend/src/App.vue` の `AVATAR_SAY_INTERVAL` / `AVATAR_SAY_DURATION` で調整できます。

## オンプレサーバー監視（node_exporter / windows_exporter）

Proxmox 配下以外のオンプレPC/サーバーは、各機に exporter を入れて監視します（Linux=node_exporter:9100 / Windows=windows_exporter:9182）。

- 監視対象は `config/hosts.toml` で定義します（雛形: `config/hosts.toml.example`）。
- 1エントリあたり `ip` / `hostname` / `display`（表示名）/ `os` / `port`（省略時OS既定）/ `group` を指定。
- `config/hosts.toml` は実設定のため git 管理外です（`.gitignore`）。

> 監視スタックを **監視対象のWindows自身のWSL上**で動かすと、WSL2ミラーモードの自己ループにより Windows ホストの exporter に到達できません（OFFLINE表示になる）。スタックは Proxmox 等、対象とは別ホストで動かしてください。

## 依存関係の管理 (uv)

Python依存関係は `uv` で管理しています。

| ファイル | 役割 |
|---|---|
| `pyproject.toml` | 必要なパッケージとバージョンを定義（`package.json` 相当） |
| `uv.lock` | 全パッケージの完全なバージョン固定（`package-lock.json` 相当） |

依存を追加・変更するときの手順：

```bash
# 1. pyproject.toml の dependencies を編集
# 2. ロックファイルを更新
uv lock
# 3. 再ビルド
docker compose up -d --build
```

`uv` のインストール：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
