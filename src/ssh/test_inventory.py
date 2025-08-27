from dotenv import load_dotenv
import yaml
import os


def load_inventory(path="src/ssh/inventory.yaml"):
    load_dotenv()
    with open(path) as f:
        inv = yaml.safe_load(f)
    defaults = inv["defaults"]
    hosts = {}
    for name, h in inv["hosts"].items():
        hosts[name] = {
            "host": h["host"],
            "username": os.getenv("SSH_USERNAME", defaults["username"]),
            "password": os.getenv("SSH_PASSWORD", defaults["password"]),
            "secret": os.getenv("SSH_SECRET", defaults.get("secret")),
            "device_type": h.get("device_type", defaults["device_type"]),
        }
    return hosts


if __name__ == "__main__":
    print(load_inventory())
