import argparse
import time
import pathlib


def timestamp():
    return time.strftime("%Y%m%d-%H%M%S")


def parse_args():
    p = argparse.ArgumentParser(description="Run show commands on devices")
    p.add_argument("--inventory", default="src/ssh/inventory.yaml")
    p.add_argument("--commands", default="src/ssh/commands.txt")
    p.add_argument("--outdir", default="outputs/show")
    p.add_argument("--save-raw", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    outdir = pathlib.Path(args.outdir) / timestamp()
    outdir.mkdir(parents=True, exist_ok=True)

    # (on remplira ici)
    print(f"Écrira les résultats dans: {outdir}")


if __name__ == "__main__":
    main()
