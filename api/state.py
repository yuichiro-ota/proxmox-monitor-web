from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppState:
    notify_enabled: bool = False
    last_snapshot: Optional[dict] = None


app_state = AppState()


def make_snapshot(report: dict) -> dict:
    nodes = {n["node"]: n["online"] for n in report["nodes"]}
    guests = {}
    for node in report["nodes"]:
        for g in node.get("vms", []) + node.get("lxc", []):
            guests[(node["node"], g["vmid"])] = {
                "name": g["name"],
                "status": g["status"],
            }
    return {"nodes": nodes, "guests": guests}


def detect_anomalies(old: dict, new: dict) -> list[str]:
    anomalies = []
    for node_name, was_online in old["nodes"].items():
        if was_online and not new["nodes"].get(node_name, False):
            anomalies.append(f"🔴 ノード *{node_name}* が OFFLINE になりました")
    for key, old_g in old["guests"].items():
        new_g = new["guests"].get(key)
        if new_g and old_g["status"] == "running" and new_g["status"] != "running":
            node, vmid = key
            anomalies.append(f"⚠️ *{old_g['name']}* (VMID:{vmid} / {node}) が停止しました")
    return anomalies
