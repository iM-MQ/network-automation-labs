# Lab 04: Python Automation

## Overview

| | |
|---|---|
| **Goal** | Replace typing `show` commands into one router at a time with Python scripts that check the whole network's health, back up every router's configuration, and detect changes that are not in the repository |
| **Runs on** | Python 3.13 in Debian on WSL2, against the [Lab 03](../lab-03-bgp) network (Containerlab and FRRouting 10.7.1) |
| **Cost** | Free. Everything runs on my computer |
| **Time** | About two hours |

In Labs 01 to 03, I checked every router by hand. Here, two scripts do it for the whole network in seconds, and say clearly whether anything is wrong:

| Script | What it does | Exit code |
|---|---|---|
| [`collect.py`](collect.py) | Finds every router, reads its OSPF neighbours, BGP sessions and routes, and reports **HEALTHY** or **UNHEALTHY** | 0 if healthy, 1 if not |
| [`backup.py`](backup.py) | Saves each router's running configuration and compares it with the repository, reporting any **drift** | 0 if no drift, 1 if any |

Both use only Python's standard library, so there is nothing to install.

---

## How it works

```
 topology-data.json ──► list of routers (no hard-coded names)
        │
        ▼
 for each router:  docker exec <router> vtysh -c "show ... json"
        │
        ▼
 Python reads the JSON ──► report ──► exit code 0 or 1
```

Three ideas carry over to real network automation:

- **An inventory, not a hard-coded list.** Containerlab writes `topology-data.json` in the lab folder, describing every node it built. `collect.py` reads it and picks out the routers by their kind, `frr`, so adding a router needs no code change.
- **Structured data, not screen-scraping.** FRR answers `show` commands in JSON when `json` is added to the end. Python reads the values by name, instead of picking numbers out of a text table whose layout could change.
- **Exit codes.** A script that ends with 0 or 1 can be used by other tools. In Lab 05, GitHub Actions will use them to pass or fail a build.

On real routers, the scripts would connect over SSH, usually with a library such as Netmiko or Scrapli, rather than `docker exec`. The rest of the approach is the same.

### The JSON the scripts read

```bash
docker exec clab-lab03-r2 vtysh -c "show bgp summary json"
```

**What I saw** (shortened):

```
"peers":{
  "10.0.23.2":{
    "hostname":"r3",
    "remoteAs":65002,
    "peerUptime":"00:00:07",
    "pfxRcd":0,
    "pfxSnt":0,
    "state":"Established",
```

The same facts as the `show bgp summary` table, but each one labelled. I ran it 7 seconds after deploying, so the session was up but no routes had crossed yet, the same "BGP waits for OSPF" effect as in Lab 03.

### The key parts of `collect.py`

Reading the inventory:

```python
def load_routers(topology_file):
    """Return {short name: container name} for every FRR router in the lab."""
    data = json.loads(Path(topology_file).read_text())
    return {
        name: node["longname"]
        for name, node in sorted(data["nodes"].items())
        if node["kind"] == "frr"
    }
```

Asking a router for JSON:

```python
def vtysh_json(container, command):
    """Run a show command on a router and return its JSON output as a dictionary."""
    result = subprocess.run(
        ["docker", "exec", container, "vtysh", "-c", f"{command} json"],
        capture_output=True,
        text=True,
        check=True,
    )
```

Reading the BGP sessions by name:

```python
    peers = data.get("ipv4Unicast", {}).get("peers", {})
    return [
        (address, peer.get("remoteAs"), peer.get("state"), peer.get("pfxRcd", 0), peer.get("pfxSnt", 0))
        for address, peer in peers.items()
    ]
```

A router is unhealthy if any OSPF neighbour is not `Full`, it has no OSPF neighbours, or any BGP session is not `Established`.

### How `backup.py` detects drift

The repository already holds every router's intended configuration, in `lab-03-bgp/<router>/frr.conf`. `backup.py` saves each running configuration to `backups/`, then compares the two with Python's `difflib`. `show running-config` adds header lines such as `Building configuration...`, so both sides are first reduced to configuration lines only, to avoid false alarms.

`backups/` is excluded by `.gitignore`. On a real network, configuration backups can contain passwords and keys, so they belong in a secured store, not in Git.

---

## Following along?

- I ran every command in a **Debian** terminal on WSL2, inside `~/network-automation-labs/lab-04-python-automation`, unless a step says otherwise.
- Each command is in its own box. Run **one line at a time**.
- Boxes marked **What I saw** show my output. They are not commands to run.

---

## How I built it

### Step 1: Started the Lab 03 network

```bash
cd ~/network-automation-labs/lab-03-bgp
```

```bash
clab deploy -t lab03.clab.yml
```

I waited about 60 seconds for OSPF, then BGP, to settle.

### Step 2: Created the scripts and excluded the backups

I created `collect.py` and `backup.py` in this folder, and added `lab-04-python-automation/backups/` and `__pycache__/` to the repository's `.gitignore`.

```bash
python3 --version
```

**What I saw:**

```
Python 3.13.5
```

---

## Tests I carried out

### Test 1: The health report

```bash
cd ~/network-automation-labs/lab-04-python-automation
```

```bash
python3 collect.py
```

**What I saw:**

```
== r1 (clab-lab03-r1)
   OSPF neighbour 2.2.2.2    on eth2  Full
   Routes: connected 4, local 3, ospf 3
== r2 (clab-lab03-r2)
   OSPF neighbour 1.1.1.1    on eth1  Full
   BGP peer 10.0.23.2  AS 65002  Established  received 2, sent 2
   Routes: bgp 2, connected 4, local 3, ospf 2
== r3 (clab-lab03-r3)
   OSPF neighbour 4.4.4.4    on eth2  Full
   BGP peer 10.0.23.1  AS 65001  Established  received 1, sent 2
   Routes: bgp 1, connected 4, local 3, ospf 2
== r4 (clab-lab03-r4)
   OSPF neighbour 3.3.3.3    on eth1  Full
   Routes: connected 4, local 3, ospf 2

HEALTHY: 4 routers checked
```

```bash
echo $?
```

**What I saw:**

```
0
```

The report shows Lab 03's filter without my looking at a single routing table: r3 received only 1 of the 2 routes Company A sent, and r4 has one fewer OSPF route than r1, because `1.1.1.1/32` never reached Company B.

### Test 2: Backups match the repository

```bash
python3 backup.py
```

**What I saw:**

```
r1: backed up, matches the repository
r2: backed up, matches the repository
r3: backed up, matches the repository
r4: backed up, matches the repository

No drift. Backups saved in backups/
```

The comparison ignored the header lines in `show running-config` correctly, so an unchanged network raised no false alarm.

### Test 3: A failure made the report UNHEALTHY

I shut down the link between the two companies:

```bash
docker exec clab-lab03-r2 vtysh -c "configure terminal" -c "interface eth2" -c "shutdown"
```

```bash
python3 collect.py
```

**What I saw:**

```
== r1 (clab-lab03-r1)
   OSPF neighbour 2.2.2.2    on eth2  Full
   Routes: connected 4, local 3, ospf 1
== r2 (clab-lab03-r2)
   OSPF neighbour 1.1.1.1    on eth1  Full
   BGP peer 10.0.23.2  AS 65002  Active  received 0, sent 0
   Routes: connected 3, local 2, ospf 2
== r3 (clab-lab03-r3)
   OSPF neighbour 4.4.4.4    on eth2  Full
   BGP peer 10.0.23.1  AS 65001  Active  received 0, sent 0
   Routes: connected 3, local 2, ospf 2
== r4 (clab-lab03-r4)
   OSPF neighbour 3.3.3.3    on eth1  Full
   Routes: connected 4, local 3, ospf 1

UNHEALTHY: 2 problem(s)
 - r2: BGP peer 10.0.23.2 is Active
 - r3: BGP peer 10.0.23.1 is Active
```

```bash
echo $?
```

**What I saw:**

```
1
```

The report pinpointed the problem: OSPF inside each company was still healthy, and only the BGP session between them was down. The knock-on effects were visible too: r1 and r4 each dropped to 1 OSPF route, because the redistributed routes from the other company were withdrawn. I brought the link back with `no shutdown`.

### Test 4: An unauthorised change was caught

I simulated someone quietly loosening Company B's filter so it accepted Company A's loopback:

```bash
docker exec clab-lab03-r3 vtysh -c "configure terminal" -c "ip prefix-list COMPANY-A-IN seq 20 permit 1.1.1.1/32"
```

```bash
python3 backup.py
```

**What I saw:**

```
r1: backed up, matches the repository
r2: backed up, matches the repository
r3: DRIFT from the repository
--- repository/r3
+++ running/r3
@@ -7,6 +7,7 @@
 ip prefix-list COMPANY-B-OUT seq 10 permit 192.168.4.0/24
 ip prefix-list COMPANY-B-OUT seq 20 permit 4.4.4.4/32
 ip prefix-list COMPANY-A-IN seq 10 permit 192.168.1.0/24
+ip prefix-list COMPANY-A-IN seq 20 permit 1.1.1.1/32
 route-map TO-COMPANY-A permit 10
  match ip address prefix-list COMPANY-B-OUT
 exit
r4: backed up, matches the repository

DRIFT on 1 router(s): r3
```

The exit code was `1`. The drift report showed exactly which router changed and the one line that was added (`+`). r2 also matched, which confirmed my `no shutdown` from Test 3 had left no trace. After I removed the line with `no ip prefix-list COMPANY-A-IN seq 20 permit 1.1.1.1/32`, `backup.py` reported no drift again.

| Test | Expected | Result |
|---|---|---|
| 1. Health report | All neighbours `Full`, both BGP sessions `Established`, exit code 0 | ✅ |
| 2. Backups | All four routers match the repository | ✅ |
| 3. Link failure | UNHEALTHY, naming both BGP sessions, exit code 1 | ✅ |
| 4. Unauthorised change | Drift on r3, showing the added line, exit code 1. Clean after reverting | ✅ |

---

## Issues I hit and how I fixed them

### 1. The interface column showed an address as well

**Symptom.** The first report showed `on eth2:10.0.12.1 Full` instead of `on eth2  Full`, which pushed the column out of line.

**Root cause.** In FRR's JSON, the OSPF neighbour's `ifaceName` field includes the interface's address. The test data I wrote the script against only had the interface name.

**Fix.** One line keeps the part before the colon:

```python
            # FRR names the interface with its address, e.g. "eth2:10.0.12.1"
            interface = entry.get("ifaceName", "?").split(":")[0]
```

**Lesson.** Test against the real system, not only sample data.

---

## Clean-up

```bash
cd ~/network-automation-labs/lab-03-bgp
```

```bash
clab destroy -t lab03.clab.yml --cleanup
```

---

## Command reference

| Command | What it does |
|---|---|
| `vtysh -c "<show command> json"` | Asks FRR for the answer as JSON |
| `python3 collect.py` | Checks every router and reports HEALTHY or UNHEALTHY |
| `python3 backup.py` | Backs up every router and reports any drift from the repository |
| `python3 <script> --topology <path>` | Points either script at a different lab's `topology-data.json` |
| `echo $?` | Shows the exit code of the last command |

## What I learned

- Reading the lab's inventory file means the scripts find routers by themselves, so the code does not change when the network does.
- JSON output turns router state into data a program can trust, instead of text it has to guess at.
- Exit codes let other tools act on a script's result, which is what makes it usable in CI.
- Comparing running configurations with the repository catches unauthorised changes, and shows exactly what changed and where.
- Configuration backups can contain secrets, so they should not go into Git.
- Sample data is not enough: the real JSON had a detail my test data did not.

---

## References

Official documentation I used while building and testing this lab.

| What I did | Documentation |
|---|---|
| Ran commands from Python | [Python: subprocess](https://docs.python.org/3/library/subprocess.html) |
| Read the JSON output | [Python: json](https://docs.python.org/3/library/json.html) |
| Compared configurations | [Python: difflib](https://docs.python.org/3/library/difflib.html) |
| Handled the script options | [Python: argparse](https://docs.python.org/3/library/argparse.html) |
| Read the inventory file Containerlab generates | [Containerlab: deploy command](https://containerlab.dev/cmd/deploy/) |
| Asked FRR for JSON output | [FRR 10.7.1: BGP user documentation](https://github.com/FRRouting/frr/blob/frr-10.7.1/doc/user/bgp.rst) |