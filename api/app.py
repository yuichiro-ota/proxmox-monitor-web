import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import urllib3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from proxmoxer import ProxmoxAPI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
BYTES_PER_GB = 1024 ** 3
SECONDS_PER_HOUR = 3600


def build_client() -> ProxmoxAPI:
    """環境変数からProxmox APIクライアントを生成する。トークン認証を優先し、なければパスワード認証を使用する。"""
    host = os.environ["PROXMOX_HOST"]
    user = os.environ["PROXMOX_USER"]
    verify_ssl = os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true"
    token_name = os.environ.get("PROXMOX_TOKEN_NAME")
    token_value = os.environ.get("PROXMOX_TOKEN_VALUE")

    if token_name and token_value:
        return ProxmoxAPI(host, user=user, token_name=token_name,
                          token_value=token_value, verify_ssl=verify_ssl)

    password = os.environ.get("PROXMOX_PASSWORD")
    if not password:
        raise RuntimeError("Set PROXMOX_TOKEN_NAME/PROXMOX_TOKEN_VALUE or PROXMOX_PASSWORD")
    return ProxmoxAPI(host, user=user, password=password, verify_ssl=verify_ssl)


def to_gb(value: int) -> float:
    """バイト値をGB単位に変換して小数点2桁で返す。"""
    return round(value / BYTES_PER_GB, 2)


def pct(used: int, total: int) -> float:
    """使用率をパーセントで返す。total が0の場合は0を返す。"""
    return round(used / total * 100, 2) if total else 0


def collect_nodes(px: ProxmoxAPI) -> list[dict]:
    """クラスター内の全ノードのステータス（CPU・メモリ・rootfs）を取得する。ステータス取得失敗時は空値で継続する。"""
    results = []
    for node in px.nodes.get():
        name = node["node"]
        try:
            status = px.nodes(name).status.get()
        except Exception as exc:
            log.warning("Cannot get status for node %s: %s", name, exc)
            status = {}

        mem = status.get("memory", {})
        rootfs = status.get("rootfs", {})
        results.append({
            "node": name,
            "online": node.get("status") == "online",
            "uptime_hours": round(status.get("uptime", 0) / SECONDS_PER_HOUR, 1),
            "cpu": {
                "cores": status.get("cpuinfo", {}).get("cpus", 0),
                "usage_pct": round(status.get("cpu", 0) * 100, 2),
            },
            "memory": {
                "total_gb": to_gb(mem.get("total", 0)),
                "used_gb": to_gb(mem.get("used", 0)),
                "free_gb": to_gb(mem.get("free", 0)),
                "usage_pct": pct(mem.get("used", 0), mem.get("total", 0)),
            },
            "rootfs": {
                "total_gb": to_gb(rootfs.get("total", 0)),
                "used_gb": to_gb(rootfs.get("used", 0)),
                "usage_pct": pct(rootfs.get("used", 0), rootfs.get("total", 0)),
            },
        })
    return results


def collect_vms(px: ProxmoxAPI, node: str) -> list[dict]:
    """指定ノードの全QEMU VMの状態（起動状態・CPU・メモリ・ディスク）を取得する。"""
    try:
        return [{
            "vmid": vm["vmid"],
            "name": vm.get("name", f"vm-{vm['vmid']}"),
            "status": vm.get("status"),
            "cpu_usage_pct": round(vm.get("cpu", 0) * 100, 2),
            "memory": {"max_gb": to_gb(vm.get("maxmem", 0)), "used_gb": to_gb(vm.get("mem", 0))},
            "disk_gb": to_gb(vm.get("maxdisk", 0)),
            "uptime_hours": round(vm.get("uptime", 0) / SECONDS_PER_HOUR, 1),
        } for vm in px.nodes(node).qemu.get()]
    except Exception as exc:
        log.warning("Cannot get VMs for node %s: %s", node, exc)
        return []


def collect_lxc(px: ProxmoxAPI, node: str) -> list[dict]:
    """指定ノードの全LXCコンテナの状態（起動状態・CPU・メモリ・ディスク）を取得する。"""
    try:
        return [{
            "vmid": ct["vmid"],
            "name": ct.get("name", f"ct-{ct['vmid']}"),
            "status": ct.get("status"),
            "cpu_usage_pct": round(ct.get("cpu", 0) * 100, 2),
            "memory": {"max_gb": to_gb(ct.get("maxmem", 0)), "used_gb": to_gb(ct.get("mem", 0))},
            "disk_gb": to_gb(ct.get("maxdisk", 0)),
            "uptime_hours": round(ct.get("uptime", 0) / SECONDS_PER_HOUR, 1),
        } for ct in px.nodes(node).lxc.get()]
    except Exception as exc:
        log.warning("Cannot get LXC for node %s: %s", node, exc)
        return []


def collect_storage(px: ProxmoxAPI, node: str) -> list[dict]:
    """指定ノードの全ストレージプールの使用量・空き容量を取得する。"""
    try:
        return [{
            "storage": s.get("storage"),
            "type": s.get("type"),
            "active": s.get("active") == 1,
            "total_gb": to_gb(s.get("total", 0)),
            "used_gb": to_gb(s.get("used", 0)),
            "avail_gb": to_gb(s.get("avail", 0)),
            "usage_pct": pct(s.get("used", 0), s.get("total", 0)),
        } for s in px.nodes(node).storage.get()]
    except Exception as exc:
        log.warning("Cannot get storage for node %s: %s", node, exc)
        return []


def fetch_report() -> dict:
    """全ノードのデータをProxmoxから収集してレポート形式のdictで返す。"""
    px = build_client()
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    nodes = collect_nodes(px)
    for node_data in nodes:
        name = node_data["node"]
        node_data["vms"] = collect_vms(px, name)
        node_data["lxc"] = collect_lxc(px, name)
        node_data["storage"] = collect_storage(px, name)
    log.info("Fetched %d node(s)", len(nodes))
    return {"collected_at": now, "nodes": nodes}


app = FastAPI(title="Proxmox Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/latest")
def get_latest():
    """Proxmoxから最新データを取得して返す。接続失敗時は503を返す。"""
    try:
        return fetch_report()
    except Exception as exc:
        log.error("Failed to fetch from Proxmox: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
