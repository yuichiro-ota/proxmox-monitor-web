import logging
from datetime import datetime, timezone, timedelta

from proxmoxer import ProxmoxAPI

from .client import build_client
from .utils import to_gb, pct, SECONDS_PER_HOUR

log = logging.getLogger(__name__)


def collect_nodes(px: ProxmoxAPI) -> list[dict]:
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
