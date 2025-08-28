import argparse
import time
import pathlib
import os
import yaml
import re
import json
from dotenv import load_dotenv
from netmiko import ConnectHandler


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
            "device_type": cfg.get("device_type"),
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


def _select_creds(host_cfg):
    """Choisit user/pass selon groups + variables d'env. Fallback = valeurs host_cfg."""
    groups = host_cfg.get("groups") or []
    if "nex" in groups:
        user = os.getenv("SSH_NEX_USERNAME") or host_cfg.get("username")
        pwd = os.getenv("SSH_NEX_PASSWORD") or host_cfg.get("password")
        # force device_type si absent
        if not host_cfg.get("device_type"):
            host_cfg["device_type"] = "cisco_nxos"
    else:
        user = os.getenv("SSH_USERNAME") or host_cfg.get("username")
        pwd = os.getenv("SSH_PASSWORD") or host_cfg.get("password")
    return user, pwd


def run_commands_on_host(host_cfg, commands):
    """
    host_cfg: dict avec host, device_type, username, password, secret, fast_cli, port
    commands: list[str]
    return: dict {cmd: output} (+ "__error__" si échec)
    """
    results = {}
    user, pwd = _select_creds(host_cfg)
    dev = {
        "device_type": host_cfg["device_type"],
        "host": host_cfg["host"],
        "username": user,
        "password": pwd,
        "fast_cli": host_cfg["fast_cli"],
        "port": host_cfg["port"],
    }
    if host_cfg.get("secret"):
        dev["secret"] = host_cfg["secret"]

    try:
        with ConnectHandler(**dev) as conn:
            if host_cfg.get("secret"):
                conn.enable()
            for cmd in commands:
                out = conn.send_command(cmd)
                results[cmd] = out
    except Exception as e:
        results["__error__"] = str(e)
    return results


def safe_name(s: str) -> str:
    return s.replace(" ", "_").replace("|", "_").replace("/", "_")


def save_results(outdir: pathlib.Path, host_name: str, results: dict, save_raw: bool):
    # JSON par host
    (outdir / f"{host_name}.json").write_text(json.dumps(results, indent=2))

    if save_raw:
        for cmd, out in results.items():
            if cmd.startswith("__"):  # ne pas créer de txt pour __error__
                continue
            (outdir / f"{host_name}__{safe_name(cmd)}.txt").write_text(out)


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
    for h in hosts:
        print(f"===> {h['name']} ({h['host']})")
        results = run_commands_on_host(h, commands)
        save_results(outdir, h["name"], results, args.save_raw)

    print(f"✔ Terminé. Résultats dans {outdir}")


if __name__ == "__main__":
    main()
