#!/usr/bin/env python3
"""Back up every router's running configuration and report any drift from the repository.

Saves each router's running configuration to backups/, then compares it with the
"golden" configuration stored for that router in the Lab 03 folder.
Exits with status 1 if any router has drifted, so other tools can act on it.
"""

import argparse
import difflib
import subprocess
import sys
from pathlib import Path

from collect import DEFAULT_TOPOLOGY, load_routers

HERE = Path(__file__).resolve().parent
BACKUP_DIR = HERE / "backups"
GOLDEN_DIR = HERE.parent / "lab-03-bgp"


def running_config(container):
    """Return a router's running configuration as text."""
    result = subprocess.run(
        ["docker", "exec", container, "vtysh", "-c", "show running-config"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def normalise(text):
    """Keep only the configuration lines, so cosmetic differences are not reported as drift."""
    lines = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip() or line.strip() in ("!", "end"):
            continue
        if line.startswith(("Building configuration", "Current configuration")):
            continue
        lines.append(line)
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY, help="Path to topology-data.json")
    args = parser.parse_args()

    BACKUP_DIR.mkdir(exist_ok=True)
    drifted = []

    for name, container in load_routers(args.topology).items():
        running = running_config(container)
        (BACKUP_DIR / f"{name}.conf").write_text(running)

        golden = (GOLDEN_DIR / name / "frr.conf").read_text()
        diff = list(
            difflib.unified_diff(
                normalise(golden),
                normalise(running),
                fromfile=f"repository/{name}",
                tofile=f"running/{name}",
                lineterm="",
            )
        )

        if diff:
            drifted.append(name)
            print(f"{name}: DRIFT from the repository")
            print("\n".join(diff))
        else:
            print(f"{name}: backed up, matches the repository")

    print()
    if drifted:
        print(f"DRIFT on {len(drifted)} router(s): {', '.join(drifted)}")
        return 1

    print(f"No drift. Backups saved in {BACKUP_DIR.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())