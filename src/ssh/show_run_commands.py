import argparse
import time
import pathlib
import os
import yaml
import re
from dotenv import load_dotenv


def timestamp():
    return time.strftime("%Y%m%d-%H%M%S")


def parse_args():
    p = argparse.ArgumentParser(description="Run show commands on devices")
    p.add_argument("--inventory", default="src/ssh/inventory.yaml")
    p.add_argument("--commands", default="src/ssh/commands.txt")
    p.add_argument("--outdir", default="outputs/show")
    p.add_argument("--save-raw", action="store_true")
    return p.parse_args()


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


def load_commands(path):
    cmds = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\r\n")  # normalise fin de ligne
            line = re.sub(r"\s+#.*$", "", line)  # enlève commentaire inline
            line = line.strip()
            if not line:  # skip vides / comment-only
                continue
            cmds.append(line)
    return cmds


def main():
    args = parse_args()
    outdir = pathlib.Path(args.outdir) / timestamp()
    outdir.mkdir(parents=True, exist_ok=True)

    # (on remplira ici)
    print(f"Écrira les résultats dans: {outdir}")
    commands = load_commands(args.commands)
    print("Commandes:", commands)
    hosts = load_inventory(args.inventory)
    print("Inventaire:", [h["name"] for h in hosts])


if __name__ == "__main__":
    main()
