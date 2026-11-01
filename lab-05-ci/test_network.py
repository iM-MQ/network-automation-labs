"""Tests that the Lab 03 network is built and behaving exactly as designed.

Run them against a deployed Lab 03 network with: python3 -m pytest -v
"""

import subprocess
import time

import pytest

from backup import GOLDEN_DIR, normalise, running_config
from collect import DEFAULT_TOPOLOGY, bgp_peers, load_routers, ospf_neighbours, vtysh_json

ROUTERS = ["r1", "r2", "r3", "r4"]

# OSPF needs about 40 seconds, and BGP only advertises once OSPF has converged
CONVERGENCE_TIMEOUT = 180


def has_route(container, prefix):
    """True if the router's routing table holds this exact prefix."""
    return prefix in vtysh_json(container, "show ip route")


def received_routes(container):
    """Number of routes received from the router's only BGP peer, or None if it has none."""
    peers = bgp_peers(container)
    return peers[0][3] if peers else None


def converged(routers):
    """True once routes have crossed BGP and been redistributed into both companies' OSPF."""
    return has_route(routers["r1"], "192.168.4.0/24") and has_route(routers["r4"], "192.168.1.0/24")


@pytest.fixture(scope="session")
def routers():
    """The lab's routers, once the network has had time to converge."""
    found = load_routers(DEFAULT_TOPOLOGY)
    deadline = time.monotonic() + CONVERGENCE_TIMEOUT
    while time.monotonic() < deadline and not converged(found):
        time.sleep(5)
    # If it never converged, carry on so the tests report exactly what is wrong
    return found


def test_inventory_lists_all_four_routers(routers):
    assert sorted(routers) == ROUTERS


@pytest.mark.parametrize("name", ROUTERS)
def test_ospf_neighbours_are_full(routers, name):
    neighbours = ospf_neighbours(routers[name])
    assert neighbours, f"{name} has no OSPF neighbours"
    assert all(state == "Full" for _, _, state in neighbours), neighbours


@pytest.mark.parametrize("name", ["r2", "r3"])
def test_bgp_session_is_established(routers, name):
    peers = bgp_peers(routers[name])
    assert len(peers) == 1, f"{name} should have exactly one BGP peer"
    assert peers[0][2] == "Established", peers


def test_company_a_accepts_both_company_b_routes(routers):
    assert received_routes(routers["r2"]) == 2


def test_company_b_filter_drops_company_a_loopback(routers):
    # r2 sends two routes, but r3's filter keeps only Company A's LAN
    assert received_routes(routers["r3"]) == 1
    assert has_route(routers["r4"], "192.168.1.0/24")
    assert not has_route(routers["r4"], "1.1.1.1/32")


def test_pc1_can_reach_pc2():
    result = subprocess.run(
        ["docker", "exec", "clab-lab03-pc1", "ping", "-c", "3", "-W", "2", "192.168.4.10"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("name", ROUTERS)
def test_running_config_matches_repository(routers, name):
    golden = (GOLDEN_DIR / name / "frr.conf").read_text()
    assert normalise(running_config(routers[name])) == normalise(golden)