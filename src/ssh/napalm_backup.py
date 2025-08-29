import os
import json
import pathlib
import time
from napalm import get_network_driver
from dotenv import load_dotenv
import yaml


def ts():
    return time.strftime("%Y%m%d-%H%M%S")


def env_interp(v):
    if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
        return os.getenv(v[2:-1], "")
    return v


def _select_creds(host_cfg):
    """Choisit user/pass selon groups + variables d'env. Fallback = valeurs host_cfg."""
    groups = host_cfg.get("groups") or []
    if "nex" in groups:  # ex: groupe pour NX-OS
        user = os.getenv("SSH_NEX_USERNAME") or host_cfg.get("username")
        pwd = os.getenv("SSH_NEX_PASSWORD") or host_cfg.get("password")
        # force device_type si absent
        if not host_cfg.get("device_type"):
            host_cfg["device_type"] = "cisco_nxos"
    else:
        user = os.getenv("SSH_USERNAME") or host_cfg.get("username")
        pwd = os.getenv("SSH_PASSWORD") or host_cfg.get("password")
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
        # sélecteur de credentials
        user, pwd = _select_creds(cfg)
        cfg["username"] = user
        cfg["password"] = pwd
        hosts.append(cfg)
    return hosts


def connect(h):
    # map vers driver NAPALM
    devtype = (h.get("device_type") or "cisco_ios").lower()
    if "xr" in devtype:
        driver = "iosxr"
    elif "nxos" in devtype:
        driver = "nxos"
    else:
        driver = "ios"

    driver_cls = get_network_driver(driver)
    optional = {}
    if h.get("secret"):
        optional["secret"] = h["secret"]
    if h.get("port"):
        optional["port"] = int(h["port"])
    dev = driver_cls(
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
        print(f"===> Backup {h['name']} ({h['host']})")
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
    print(f"✔ backups in {outdir}")


if __name__ == "__main__":
    main()
