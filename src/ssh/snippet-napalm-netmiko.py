#!/usr/bin/env python3
# napalm_or_netmiko_apply.py
import argparse
import pathlib
import sys
import os
import copy
import yaml
from typing import Any, Dict, List
from netmiko import ConnectHandler  # file_transfer kept for IOS path

# optional .env support (for ${SSH_*} in YAML)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


# ------------------------------
# Inventory helpers
# ------------------------------
def _expand_env_val(v: Any) -> Any:
    if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
        return os.getenv(v[2:-1], "")
    return v


def _deep_expand_env(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _deep_expand_env(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_deep_expand_env(v) for v in x]
    return _expand_env_val(x)


def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(a) if a else {}
    for k, v in (b or {}).items():
        out[k] = v
    return out


def _to_bool(val: Any) -> Any:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return val


def _materialize_host(
    name: str, cfg: Dict[str, Any], defaults: Dict[str, Any], groups_def: Dict[str, Any]
) -> Dict[str, Any]:
    """
    defaults -> groups -> host, then expand ${ENV}, and coerce types.
    NOTE: dest_file_system can be set in YAML; otherwise we'll auto-pick later.
    """
    base = copy.deepcopy(defaults or {})
    for g in cfg.get("groups") or []:
        if groups_def and g in groups_def:
            base = _merge(base, groups_def[g])
    base = _merge(base, cfg or {})
    base["name"] = name

    base = _deep_expand_env(base)

    if "fast_cli" in base:
        base["fast_cli"] = _to_bool(base["fast_cli"])
    if "port" in base:
        try:
            base["port"] = int(base["port"])
        except Exception:
            pass
    if "use_scp" in base:
        base["use_scp"] = _to_bool(base["use_scp"])

    return base


def load_inventory(path: str | None = None) -> List[Dict[str, Any]]:
    inv_file = pathlib.Path(path or "inventory.yaml")
    if not inv_file.exists():
        raise FileNotFoundError(f"Inventaire non trouvé: {inv_file}")

    data = yaml.safe_load(inv_file.read_text()) or {}

    # Nornir-style {defaults, groups, hosts: {name: cfg}}
    if isinstance(data, dict) and "hosts" in data and isinstance(data["hosts"], dict):
        defaults = data.get("defaults", {}) or {}
        groups_def = data.get("groups", {}) or {}
        out = []
        for name, cfg in data["hosts"].items():
            out.append(_materialize_host(name, cfg or {}, defaults, groups_def))
        return out

    # Simple formats
    if isinstance(data, dict) and isinstance(data.get("hosts"), list):
        return data["hosts"]
    if isinstance(data, list):
        return data

    raise ValueError(
        "inventory.yaml invalide: attendu Nornir-style ou une liste d'hôtes."
    )


# ------------------------------
# Creds + platform mapping
# ------------------------------
def select_creds(h: Dict[str, Any]):
    user = (h.get("username") or "").strip()
    pwd = (h.get("password") or "").strip()
    devt = (h.get("device_type") or "").lower()

    if not user or not pwd:
        if "nx" in devt:
            user = user or os.getenv("SSH_NEX_USERNAME", "")
            pwd = pwd or os.getenv("SSH_NEX_PASSWORD", "")
        elif "xr" in devt:
            user = user or os.getenv("SSH_XR_USERNAME", "")
            pwd = pwd or os.getenv("SSH_XR_PASSWORD", "")
        else:
            user = user or os.getenv("SSH_USERNAME", "")
            pwd = pwd or os.getenv("SSH_PASSWORD", "")

    if not user or not pwd:
        raise RuntimeError(
            f"Credentials manquants pour {h.get('name') or h.get('host')}: "
            "définis username/password via defaults/groups/host, .env, ou variables d'environnement."
        )
    return user, pwd


def _napalm_driver(devtype: str | None) -> str:
    dt = (devtype or "cisco_ios").lower()
    if "xr" in dt:
        return "iosxr"
    if "nx" in dt:
        return "nxos_ssh"  # SSH transport for Nexus
    return "ios"


def _netmiko_driver(devtype: str | None) -> str:
    dt = (devtype or "cisco_ios").lower()
    if "xr" in dt:
        return "cisco_xr"
    if "nx" in dt:
        return "cisco_nxos"
    return "cisco_ios"


def _default_fs_for(devtype: str | None) -> str | None:
    dt = (devtype or "").lower()
    if "nx" in dt:
        return "bootflash:"
    if "xr" in dt:
        return "disk0:"
    return "flash:"  # IOS/IOS-XE


# ------------------------------
# NAPALM path
# ------------------------------
def connect_napalm(h: Dict[str, Any], cli_dest_fs: str | None = None):
    from napalm import get_network_driver

    user, pwd = select_creds(h)
    driver = _napalm_driver(h.get("device_type"))
    drv = get_network_driver(driver)

    dest_fs = (
        h.get("dest_file_system")
        or cli_dest_fs
        or _default_fs_for(h.get("device_type"))
    )

    optional = {}
    if h.get("secret"):
        optional["secret"] = h["secret"]
    if h.get("port"):
        optional["port"] = int(h["port"])
    if "fast_cli" in h:
        optional["fast_cli"] = _to_bool(h["fast_cli"])
    if dest_fs:
        optional["dest_file_system"] = dest_fs
    if "use_scp" in h:
        optional["use_scp"] = _to_bool(h["use_scp"])  # false => try SFTP

    dev = drv(
        hostname=h["host"],
        username=user,
        password=pwd,
        optional_args=optional,
        timeout=90,
    )
    dev.open()
    return dev


def _is_scp_disabled_error(e: Exception) -> bool:
    s = str(e).lower()
    return (
        "scp file transfers are not enabled" in s
        or "ip scp server enable" in s
        or "feature scp-server" in s
    )


def _normalize_snippet_text(snippet_path: pathlib.Path) -> str:
    lines_out = []
    for raw in snippet_path.read_text().splitlines():
        s = raw.rstrip()
        if not s or s.lstrip().startswith(("!", "#")):
            continue
        # Handle YAML bullets turning into '- <cmd>'
        if s.lstrip().startswith("- "):
            s = s.lstrip()[2:]  # drop "- "
        elif s.lstrip().startswith("-") and not s.lstrip().startswith("--"):
            # handles cases like "-no shutdown" -> "no shutdown"
            s = s.lstrip()[1:].lstrip()
        lines_out.append(s)
    return "\n".join(lines_out) + "\n"


def napalm_merge(
    hosts: List[Dict[str, Any]],
    snippet_path: pathlib.Path,
    commit: bool,
    cli_dest_fs: str | None,
):
    if not snippet_path or not snippet_path.exists():
        raise FileNotFoundError(f"Snippet not found: {snippet_path.resolve()}")
    cfg_text = _normalize_snippet_text(snippet_path)

    for h in hosts:
        name = h.get("name") or h.get("host")
        print(f"\n===> Merge on {name} ({h.get('host')}) groups={h.get('groups')}")
        try:
            dev = connect_napalm(h, cli_dest_fs=cli_dest_fs)
            # IMPORTANT: feed config text directly (avoid filename path issues)
            cfg_text = pathlib.Path("snippet.cfg").read_text()
            dev.load_merge_candidate(config=cfg_text)
            diff = (dev.compare_config() or "").strip()
            if not diff:
                print("No change, discard.")
                dev.discard_config()
            else:
                print("DIFF:\n", diff)
                if commit:
                    dev.commit_config()
                    print("✔ committed")
                else:
                    dev.discard_config()
                    print("ℹ discarded (use --commit to apply)")
            dev.close()
        except Exception as e:
            # same fallback you already had
            if _is_scp_disabled_error(e):
                print(f"⚠ SCP disabled on {name}.", end=" ")
                if not commit:
                    print(
                        "Dry-run requested → skipping fallback to avoid changing running-config."
                    )
                    continue
                print("Falling back to Netmiko (send_config_set / NX SCP).")
                try:
                    netmiko_push(
                        [h], snippet_path, commit=True, cli_dest_fs=cli_dest_fs
                    )
                except Exception as ee:
                    print(f"ERROR {name} (fallback): {type(ee).__name__}: {ee}")
            else:
                print(f"ERROR {name}: {type(e).__name__}: {e}")


# ------------------------------
# Netmiko helpers for NX-OS
# ------------------------------
def _nx_try_dir(conn, fs: str) -> bool:
    """Return True if 'dir <fs>' looks usable on this box."""
    out = conn.send_command(
        f"dir {fs}", expect_string=r"#", strip_prompt=False, strip_command=False
    )
    bad = ("No such file or directory", "Error", "Invalid", "not found")
    return not any(b in out for b in bad)


def _nx_pick_fs(conn, h: Dict[str, Any], cli_dest_fs: str | None) -> str:
    """Pick a working filesystem for NX-OS without relying on Netmiko free-space parsing."""
    candidates = []
    if cli_dest_fs:
        candidates.append(cli_dest_fs)
    if h.get("dest_file_system"):
        candidates.append(h["dest_file_system"])
    # common on NX-OS/labs
    candidates += ["bootflash:", "flash:", "volatile:", "logflash:"]
    tried = []
    for fs in candidates:
        if fs in tried:
            continue
        tried.append(fs)
        try:
            if _nx_try_dir(conn, fs):
                return fs
        except Exception:
            pass
    raise RuntimeError(
        f"Could not find a working filesystem on {h.get('name') or h.get('host')}. "
        f"Tried: {', '.join(tried)}. Override with --dest-fs or inventory.dest_file_system."
    )


# ------------------------------
# Netmiko path (direct push)
# ------------------------------
def connect_netmiko(h: Dict[str, Any]):
    user, pwd = select_creds(h)
    device_type = _netmiko_driver(h.get("device_type"))

    params = {
        "device_type": device_type,
        "host": h["host"],
        "username": user,
        "password": pwd,
    }
    if h.get("port"):
        params["port"] = int(h["port"])
    if h.get("secret"):
        params["secret"] = h["secret"]  # enable secret (IOS/IOS-XE)

    # DO NOT pass dest_file_system here (would break BaseConnection.__init__)
    return ConnectHandler(**params)


def _load_snippet_lines(snippet_path: pathlib.Path) -> List[str]:
    lines = []
    for raw in snippet_path.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("!") or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def _nx_dest_fs(h: Dict[str, Any], cli_dest_fs: str | None) -> str:
    # CLI override > inventory > default
    return (
        cli_dest_fs
        or h.get("dest_file_system")
        or _default_fs_for(h.get("device_type"))
        or "bootflash:"
    )


def netmiko_push(
    hosts: List[Dict[str, Any]],
    snippet_path: pathlib.Path,
    commit: bool,
    cli_dest_fs: str | None = None,
):
    cmds = _load_snippet_lines(snippet_path)
    for h in hosts:
        name = h.get("name") or h.get("host")
        devt = (h.get("device_type") or "").lower()
        print(
            f"\n===> Netmiko push on {name} ({h.get('host')}) groups={h.get('groups')}"
        )

        if "xr" in devt:
            print(f"⏭ Skipping {name} (IOS-XR not supported in this Netmiko mode)")
            continue

        try:
            conn = connect_netmiko(h)

            if "nx" in devt:
                # --- NX-OS: ALWAYS use raw SCPConn (avoid Netmiko file_transfer free-space parse) ---
                _ = conn.send_command("terminal length 0", expect_string=r"#")
                fs = _nx_pick_fs(conn, h, cli_dest_fs)

                # Push file via SCP over the current SSH session
                try:
                    try:
                        from netmiko import SCPConn
                    except Exception:
                        from netmiko.scp_handler import SCPConn  # older netmiko
                    scp = SCPConn(conn)
                    scp.scp_transfer_file(str(snippet_path), f"{fs}merge.cfg")
                    scp.close()
                except Exception as scpe:
                    raise RuntimeError(
                        f"SCP failed on {name} to {fs}merge.cfg: {scpe}"
                    ) from scpe

                # (optional) verify presence
                _ = conn.send_command(f"dir {fs} | i merge.cfg", expect_string=r"#")

                # Apply the uploaded file
                out = conn.send_command(
                    f"copy {fs}merge.cfg running-config", expect_string=r"\[yes/no\]|#"
                )
                if "[yes/no]" in out:
                    out += "\n" + conn.send_command("yes", expect_string=r"#")
                print(out)

            else:
                # --- IOS / IOS-XE: push lines directly ---
                out = conn.send_config_set(cmds)
                print(out)

            if commit:
                if "nx" in devt:
                    save = conn.send_command(
                        "copy running-config startup-config",
                        expect_string=r"\[yes/no\]|#",
                    )
                    if "[yes/no]" in save:
                        save += "\n" + conn.send_command("yes", expect_string=r"#")
                    print(save)
                else:
                    print(conn.save_config())

            conn.disconnect()

        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")


# ------------------------------
# Interactive group helpers
# ------------------------------
def _collect_all_groups(hosts):
    s = set()
    for h in hosts:
        for g in h.get("groups") or []:
            s.add(str(g))
    return sorted(s, key=lambda x: x.lower())


def _prompt_groups(groups):
    if not groups:
        print("No groups detected; applying to all hosts.")
        return []
    print("\nAvailable groups:")
    for idx, g in enumerate(groups, 1):
        print(f"  {idx}. {g}")
    print("Choose groups (comma-separated), or press Enter for ALL:")
    resp = input("> ").strip()
    if not resp:
        return []
    selected = set()
    for token in resp.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            i = int(token)
            if 1 <= i <= len(groups):
                selected.add(groups[i - 1])
        else:
            if token in groups:
                selected.add(token)
    return sorted(selected, key=lambda x: x.lower())


# ------------------------------
# CLI
# ------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="NAPALM/Netmiko config apply (inventory.yaml; filesystem override via --dest-fs or inventory.dest_file_system)"
    )
    ap.add_argument(
        "--snippet", help="Path to config snippet (required unless --print-hosts)"
    )
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Commit/save changes (NAPALM=commit, Netmiko=save to startup-config)",
    )
    ap.add_argument("--inventory", help="Path to inventory (default=./inventory.yaml)")
    ap.add_argument(
        "--engine",
        choices=["napalm", "netmiko"],
        default="napalm",
        help="Apply via napalm (merge) or netmiko (send_config_set/NX SCP copy)",
    )
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only on hosts whose name contains this (repeatable)",
    )
    ap.add_argument(
        "--skip",
        action="append",
        default=["IOS_XRv", "Ubuntu_Devbox"],
        help="Skip hosts whose name contains this (repeatable)",
    )
    ap.add_argument(
        "--group",
        action="append",
        default=[],
        help="Apply only to hosts that belong to this group (repeatable)",
    )
    ap.add_argument(
        "--print-hosts", action="store_true", help="Print materialized hosts and exit"
    )
    ap.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable interactive prompts (CI mode)",
    )
    ap.add_argument(
        "--dest-fs",
        help="Override remote filesystem (e.g., bootflash:, flash:, volatile:, logflash:)",
    )
    args = ap.parse_args()

    # allow --print-hosts without --snippet
    if not args.print_hosts and not args.snippet:
        ap.error("--snippet is required unless --print-hosts is used")

    try:
        hosts = load_inventory(args.inventory)
    except Exception as e:
        sys.exit(f"Erreur chargement inventaire: {e}")

    # interactive group selection if none provided and TTY
    if (
        not args.group
        and sys.stdin.isatty()
        and sys.stdout.isatty()
        and not args.no_interactive
    ):
        all_groups = _collect_all_groups(hosts)
        chosen = _prompt_groups(all_groups)
        args.group = chosen  # [] means ALL

    if args.print_hosts:
        import json

        print(json.dumps(hosts, indent=2))
        return

    # filter
    needles = [s.lower() for s in (args.only or [])]
    skippers = [s.lower() for s in (args.skip or [])]
    groupsel = [s.lower() for s in (args.group or [])]

    selected = []
    for h in hosts:
        name = (h.get("name") or h.get("host") or "").strip()
        lname = name.lower()
        host_groups = [gg.lower() for gg in (h.get("groups") or [])]

        if skippers and any(p in lname for p in skippers):
            print(f"⏭ Skipping {name}")
            continue
        if needles and not any(p in lname for p in needles):
            continue
        if groupsel and not any(g in host_groups for g in groupsel):
            continue

        selected.append(h)

    if not selected:
        sys.exit("Inventaire vide (ou filtres --only/--skip/--group trop restrictifs).")

    snip = pathlib.Path(args.snippet) if args.snippet else None
    if snip and not snip.exists():
        sys.exit(f"snippet not found: {snip}")

    # apply
    if args.engine == "napalm":
        napalm_merge(selected, snip, args.commit, cli_dest_fs=args.dest_fs)
    else:
        netmiko_push(selected, snip, args.commit, cli_dest_fs=args.dest_fs)


if __name__ == "__main__":
    main()
