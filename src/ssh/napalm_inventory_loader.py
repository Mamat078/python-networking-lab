import os
import yaml
from dotenv import load_dotenv


def env_interp(v):
    if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
        return os.getenv(v[2:-1], "")
    return v


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

        # map device_type -> NAPALM driver
        devtype = (cfg.get("device_type") or "cisco_ios").lower()
        if devtype in ("cisco_ios", "ios", "iosxe", "cisco_xe"):
            driver = "ios"
        elif devtype in ("cisco_xr", "iosxr", "xr"):
            driver = "iosxr"
        elif devtype in ("cisco_nxos", "nxos"):
            driver = "nxos"
        else:
            driver = "ios"  # fallback raisonnable

        hosts.append(
            {
                "name": name,
                "driver": driver,
                "host": cfg["host"],
                "username": cfg.get("username"),
                "password": cfg.get("password"),
                "secret": cfg.get("secret") or os.getenv("ENABLE_SECRET") or None,
                "optional_args": {k: cfg[k] for k in ("port",) if k in cfg},
            }
        )
    return hosts
