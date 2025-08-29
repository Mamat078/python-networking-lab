# src/ssh/napalm_backup_all.py
import os
import json
import pathlib
import time
import yaml
from napalm import get_network_driver
from dotenv import load_dotenv


def ts():
    return time.strftime("%Y%m%d-%H%M%S")


def env_interp(v):
    if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
        return os.getenv(v[2:-1], "")
    return v


def _select_creds(host_cfg):
    """Choisit les credentials en fonction du groupe."""
    groups = host_cfg.get("groups", [])
    # Host override direct
    user = host_cfg.get("username")
    pwd = host_cfg.get("password")

    if "nex" in groups:  # NX-OS
        user = user or os.getenv("SSH_NEX_USERNAME")
        pwd = pwd or os.getenv("SSH_NEX_PASSWORD")
        if not host_cfg.get("device_type"):
            host_cfg["device_type"] = "cisco_nxos"

    else:  # par défaut IOS/IOS-XE
        user = user or os.getenv("SSH_USERNAME")
        pwd = pwd or os.getenv("SSH_PASSWORD")
        if not host_cfg.get("device_type"):
            host_cfg["device_type"] = "cisco_ios"

    return user, pwd


def load_inventory(path="src/ssh/inventory.yaml"):
    load_dotenv()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    defaults = {k: env_interp(v) for k, v in (data.get("defaults") or {}).items()}
    hosts = []
    for name, h in (data.get("hosts") or {}).items():
        h = {k: env_interp(v) for k, v in (h or {}).items()}
        cfg = dict(defaults)
        cfg.update(h)
        cfg["name"] = name
        user, pwd = _select_creds(cfg)
        cfg["username"], cfg["password"] = user, pwd
        hosts.append(cfg)
    return hosts


def connect(h):
    devtype = (h.get("device_type") or "cisco_ios").lower()
    if "xr" in devtype:
        driver = "iosxr"
    elif "nxos" in devtype:
        driver = "nxos"
    else:
        driver = "ios"

    drv = get_network_driver(driver)
    optional = {}
    if h.get("secret"):
        optional["secret"] = h["secret"]
    if h.get("port"):
        optional["port"] = int(h["port"])
    dev = drv(
        hostname=h["host"],
        username=h["username"],
        password=h["password"],
        optional_args=optional,
        timeout=60,
    )
    dev.open()
    return dev


def main():
    outdir = pathlib.Path("outputs/napalm_backups") / ts()
    outdir.mkdir(parents=True, exist_ok=True)
    results = []

    for h in load_inventory():
        if h["name"] in ("IOS_XRv", "Ubuntu_Devbox"):
            print(f"⏭ Skipping {h['name']} ({h['host']})")
            continue  # on saute uniquement ce host

        print(f"===> Backup {h['name']} ({h['host']}) group={h.get('groups')}")
        entry = {"host": h["name"], "ip": h["host"], "ok": False}
        try:
            dev = connect(h)
            cfgs = dev.get_config()
            (outdir / f"{h['name']}.running.cfg").write_text(cfgs.get("running", ""))
            if cfgs.get("startup"):
                (outdir / f"{h['name']}.startup.cfg").write_text(cfgs["startup"])
            facts = dev.get_facts()
            (outdir / f"{h['name']}.facts.json").write_text(json.dumps(facts, indent=2))
            dev.close()
            entry["ok"] = True
        except Exception as e:
            (outdir / f"{h['name']}_ERROR.txt").write_text(f"{type(e).__name__}: {e}")
            entry["error"] = f"{type(e).__name__}: {e}"
        results.append(entry)

    (outdir / "_summary.json").write_text(json.dumps(results, indent=2))
    print(f"✔ backups saved in {outdir}")


if __name__ == "__main__":
    main()
