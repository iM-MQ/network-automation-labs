#!/usr/bin/env python3
"""Check the health of every router in a Containerlab network.

Reads the routers from Containerlab's topology-data.json, asks each one for its
OSPF neighbours, BGP sessions and routes as JSON, and prints a report.
Exits with status 1 if anything is unhealthy, so other tools can act on it.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# The Lab 03 network, which this lab automates
DEFAULT_TOPOLOGY = (
    Path(__file__).resolve().parent.parent / "lab-03-bgp" / "clab-lab03" / "topology-data.json"
)


def load_routers(topology_file):
    """Return {short name: container name} for every FRR router in the lab."""
    data = json.loads(Path(topology_file).read_text())
    return {
        name: node["longname"]
        for name, node in sorted(data["nodes"].items())
        if node["kind"] == "frr"
    }


def vtysh_json(container, command):
    """Run a show command on a router and return its JSON output as a dictionary."""
    result = subprocess.run(
        ["docker", "exec", container, "vtysh", "-c", f"{command} json"],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # A router that does not run this protocol may not answer in JSON
        return {}


def ospf_neighbours(container):
    """Return a list of (neighbour router ID, interface, state)."""
    data = vtysh_json(container, "show ip ospf neighbor")
    found = []
    for router_id, entries in data.get("neighbors", {}).items():
        for entry in entries:
                                    # FRR names the interface with its address, e.g. "eth2:10.0.12.1"
            interface = entry.get("ifaceName", "?").split(":")[0]
            found.append((router_id, interface, entry.get("converged", "?")))
    return found


def bgp_peers(container):
    """Return a list of (peer address, remote AS, state, routes received, routes sent)."""
    data = vtysh_json(container, "show bgp summary")
    peers = data.get("ipv4Unicast", {}).get("peers", {})
    return [
        (address, peer.get("remoteAs"), peer.get("state"), peer.get("pfxRcd", 0), peer.get("pfxSnt", 0))
        for address, peer in peers.items()
    ]


def route_counts(container):
    """Return {protocol: number of selected routes}, for example {"ospf": 3}."""
    data = vtysh_json(container, "show ip route")
    counts = {}
    for entries in data.values():
        for entry in entries:
            if entry.get("selected"):
                counts[entry["protocol"]] = counts.get(entry["protocol"], 0) + 1
    return dict(sorted(counts.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY, help="Path to topology-data.json")
    args = parser.parse_args()

    routers = load_routers(args.topology)
    problems = []

    for name, container in routers.items():
        print(f"== {name} ({container})")

        neighbours = ospf_neighbours(container)
        for router_id, interface, state in neighbours:
            print(f"   OSPF neighbour {router_id:<10} on {interface:<5} {state}")
            if state != "Full":
                problems.append(f"{name}: OSPF neighbour {router_id} is {state}")
        if not neighbours:
            problems.append(f"{name}: no OSPF neighbours")

        for address, remote_as, state, received, sent in bgp_peers(container):
            print(f"   BGP peer {address:<10} AS {remote_as}  {state}  received {received}, sent {sent}")
            if state != "Established":
                problems.append(f"{name}: BGP peer {address} is {state}")

        counts = route_counts(container)
        print("   Routes: " + ", ".join(f"{protocol} {count}" for protocol, count in counts.items()))

    print()
    if problems:
        print(f"UNHEALTHY: {len(problems)} problem(s)")
        for problem in problems:
            print(f" - {problem}")
        return 1

    print(f"HEALTHY: {len(routers)} routers checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())