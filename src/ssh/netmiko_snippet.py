#!/usr/bin/env python3
# netmiko_apply.py  (Netmiko-only, robust NX-OS handling)
import argparse
import pathlib
import sys
import os
import copy
import yaml
from typing import Any, Dict, List
from netmiko import ConnectHandler

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
    return base


def load_inventory(path: str | None = None) -> List[Dict[str, Any]]:
    inv_file = pathlib.Path(path or "inventory.yaml")
    if not inv_file.exists():
        raise FileNotFoundError(f"Inventory not found: {inv_file}")
    data = yaml.safe_load(inv_file.read_text()) or {}

    if isinstance(data, dict) and "hosts" in data and isinstance(data["hosts"], dict):
        defaults = data.get("defaults", {}) or {}
        groups_def = data.get("groups", {}) or {}
        out = []
        for name, cfg in data["hosts"].items():
            out.append(_materialize_host(name, cfg or {}, defaults, groups_def))
        return out
    if isinstance(data, dict) and isinstance(data.get("hosts"), list):
        return data["hosts"]
    if isinstance(data, list):
        return data
    raise ValueError("Invalid inventory: expected Nornir-style or a list of hosts.")


# ------------------------------
# Platform helpers
# ------------------------------
def _netmiko_driver(devtype: str | None) -> str:
    dt = (devtype or "cisco_ios").lower()
    if "xr" in dt:
        return "cisco_xr"
    if "nx" in dt:
        return "cisco_nxos"
    return "cisco_ios"


def _default_fs_for(devtype: str | None) -> str:
    dt = (devtype or "").lower()
    if "nx" in dt:
        return "bootflash:"
    if "xr" in dt:
        return "disk0:"
    return "flash:"


# ------------------------------
# Connection + snippet
# ------------------------------
def select_creds(h: Dict[str, Any]):
    user = (h.get("username") or "").strip()
    pwd = (h.get("password") or "").strip()
    dt = (h.get("device_type") or "").lower()
    if not user or not pwd:
        if "nx" in dt:
            user = user or os.getenv("SSH_NEX_USERNAME", "")
            pwd = pwd or os.getenv("SSH_NEX_PASSWORD", "")
        elif "xr" in dt:
            user = user or os.getenv("SSH_XR_USERNAME", "")
            pwd = pwd or os.getenv("SSH_XR_PASSWORD", "")
        else:
            user = user or os.getenv("SSH_USERNAME", "")
            pwd = pwd or os.getenv("SSH_PASSWORD", "")
    if not user or not pwd:
        raise RuntimeError(f"Missing credentials for {h.get('name') or h.get('host')}")
    return user, pwd


def connect_netmiko(h: Dict[str, Any]):
    user, pwd = select_creds(h)
    params = {
        "device_type": _netmiko_driver(h.get("device_type")),
        "host": h["host"],
        "username": user,
        "password": pwd,
    }
    if h.get("port"):
        params["port"] = int(h["port"])
    if h.get("secret"):
        params["secret"] = h["secret"]  # IOS/IOS-XE enable
    # Optional session log:
    # params["session_log"] = f"netmiko_{h.get('name','device')}.log"
    return ConnectHandler(**params)


def _normalize_snippet_lines(snippet_path: pathlib.Path) -> List[str]:
    """Return clean CLI lines (remove blank, comments, YAML bullets)."""
    out = []
    for raw in snippet_path.read_text().splitlines():
        s = raw.rstrip()
        if not s:
            continue
        if s.lstrip().startswith(("!", "#")):
            continue
        t = s.lstrip()
        if t.startswith("- "):  # "- command"
            t = t[2:]
        elif t.startswith("-") and not t.startswith(
            "--"
        ):  # "-no shutdown" -> "no shutdown"
            t = t[1:].lstrip()
        out.append(t)
    return out


# ------------------------------
# NX-OS helpers
# ------------------------------
def _nx_try_dir(conn, fs: str) -> bool:
    try:
        out = conn.send_command(
            f"dir {fs}", expect_string=r"#", strip_prompt=False, strip_command=False
        )
    except Exception:
        return False
    bad = ("No such file or directory", "Error", "Invalid", "not found")
    return not any(b in out for b in bad)


def _nx_pick_fs(conn, h: Dict[str, Any], cli_dest_fs: str | None) -> str:
    cand = []
    if cli_dest_fs:
        cand.append(cli_dest_fs)
    if h.get("dest_file_system"):
        cand.append(h["dest_file_system"])
    cand += ["bootflash:", "flash:", "volatile:", "logflash:"]
    seen = set()
    for fs in cand:
        if fs in seen:
            continue
        seen.add(fs)
        if _nx_try_dir(conn, fs):
            return fs
    # last resort: just return something; copy might still work
    return cli_dest_fs or h.get("dest_file_system") or "bootflash:"


# ------------------------------
# Push logic (Netmiko only)
# ------------------------------
def netmiko_push(
    hosts: List[Dict[str, Any]],
    snippet_path: pathlib.Path,
    commit: bool,
    cli_dest_fs: str | None = None,
):
    if not snippet_path.exists():
        raise FileNotFoundError(f"Snippet not found: {snippet_path}")
    cmds = _normalize_snippet_lines(snippet_path)

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
            _ = conn.send_command("terminal length 0", expect_string=r"#")

            if "nx" in devt:
                # Try SCP copy; fallback to direct CLI lines
                scp_ok = False
                try:
                    fs = _nx_pick_fs(
                        conn, h, cli_dest_fs or _default_fs_for(h.get("device_type"))
                    )
                    # verify FS (best effort)
                    _ = conn.send_command(f"dir {fs}", expect_string=r"#")
                    # raw SCP (no free-space parsing)
                    try:
                        try:
                            from netmiko import SCPConn
                        except Exception:
                            from netmiko.scp_handler import SCPConn
                        scp = SCPConn(conn)
                        scp.scp_transfer_file(str(snippet_path), f"{fs}merge.cfg")
                        scp.close()
                        # apply the uploaded file
                        out = conn.send_command(
                            f"copy {fs}merge.cfg running-config",
                            expect_string=r"\[yes/no\]|#",
                        )
                        if "[yes/no]" in out:
                            out += "\n" + conn.send_command("yes", expect_string=r"#")
                        print(out)
                        scp_ok = True
                    except Exception as scpe:
                        print(f"⚠ SCP failed on {name}: {scpe}")
                except Exception as pre:
                    print(f"⚠ NX FS probe failed on {name}: {pre}")

                if not scp_ok:
                    print(f"→ Fallback to direct CLI push on {name}")
                    out = conn.send_config_set(cmds, exit_config_mode=False)
                    print(out)
                    try:
                        conn.exit_config_mode()
                    except Exception:
                        pass

            else:
                # IOS / IOS-XE: just push lines
                out = conn.send_config_set(cmds)
                print(out)

            if commit:
                save = conn.send_command(
                    "copy running-config startup-config", expect_string=r"\[yes/no\]|#"
                )
                if "[yes/no]" in save:
                    save += "\n" + conn.send_command("yes", expect_string=r"#")
                print(save)

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
        description="Netmiko-only config apply (inventory.yaml)"
    )
    ap.add_argument("--snippet", required=True, help="Path to config snippet")
    ap.add_argument(
        "--commit", action="store_true", help="Save to startup-config after push"
    )
    ap.add_argument("--inventory", help="Path to inventory (default=./inventory.yaml)")
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
        help="Override NX-OS filesystem (e.g., bootflash:, flash:, volatile:, logflash:)",
    )
    args = ap.parse_args()

    try:
        hosts = load_inventory(args.inventory)
    except Exception as e:
        sys.exit(f"Inventory load error: {e}")

    if args.print_hosts:
        import json

        print(json.dumps(hosts, indent=2))
        return

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
        sys.exit("No hosts selected (filters too restrictive).")

    snip = pathlib.Path(args.snippet)
    if not snip.exists():
        sys.exit(f"Snippet not found: {snip}")

    # apply
    netmiko_push(selected, snip, args.commit, cli_dest_fs=args.dest_fs)


if __name__ == "__main__":
    main()
