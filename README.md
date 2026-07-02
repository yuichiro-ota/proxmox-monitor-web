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
PROXMOX_HOST=192.168.100.40       # ProxmoxのIPまたはFQDN (https://不要)
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

- ページを開いたとき・手動更新・10秒ごとの自動更新のたびに `/api/latest` を叩く
- `back` コンテナがそのつどProxmox APIへ接続してライブデータを返す
- データはファイルに保存しない（ステートレス）

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
