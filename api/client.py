import os

import urllib3
from proxmoxer import ProxmoxAPI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def build_client() -> ProxmoxAPI:
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
