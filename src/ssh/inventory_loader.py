import os
import yaml
from dotenv import load_dotenv


def env_interp(v):
    if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
        return os.getenv(v[2:-1], "")
    return v


def load_inventory(path):
    load_dotenv()  # lit .env
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    defaults = {k: env_interp(v) for k, v in (data.get("defaults") or {}).items()}
    hosts = []
    for name, h in (data.get("hosts") or {}).items():
        h = {k: env_interp(v) for k, v in (h or {}).items()}
        cfg = dict(defaults)
        cfg.update(h)  # defaults < host
        host_cfg = {
            "name": name,
            "host": cfg["host"],
            "device_type": cfg.get("device_type", "cisco_ios"),
            "username": cfg.get("username"),
            "password": cfg.get("password"),
            "secret": cfg.get("secret"),
            "fast_cli": bool(cfg.get("fast_cli", True)),
            "port": int(cfg.get("port", 22)),
        }
        hosts.append(host_cfg)
    return hosts
