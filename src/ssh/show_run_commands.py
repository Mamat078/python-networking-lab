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


def load_commands(path):
    with open(path) as f:
        cmds = []
        for line in f:
            # supprimer espaces en début/fin
            line = line.strip()
            if not line:
                continue
            # couper au premier #
            if "#" in line:
                line = line.split("#", 1)[0].strip()
            if line:  # éviter d'ajouter une chaîne vide
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


if __name__ == "__main__":
    main()
