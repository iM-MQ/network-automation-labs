# Lab 01: Static Routing

## Overview

| | |
|---|---|
| **Goal** | Build a three-router network, route between two LANs with static routes only, and see exactly where traffic stops while routes are missing |
| **Runs on** | Containerlab and FRRouting 10.7.1, in Debian on WSL2 |
| **Cost** | Free. Everything runs on my computer |
| **Time** | About three hours, including setting up Containerlab |

I configured the routes one router at a time, testing after each, to find every point where traffic fails. The most useful finding was that a missing route often produces **silence** rather than an error, because the error message has no way back either.

---

## Topology

```
 pc1 ─────── r1 ─────────── r2 ─────────── r3 ─────── pc2
     .10  .1    .1       .2    .1       .2    .1  .10
  192.168.1.0/24  10.0.12.0/30   10.0.23.0/30  192.168.3.0/24
      (eth1)    (eth2)  (eth1)  (eth2)  (eth1)  (eth2)
```

| Device | Interface | Address | Connects to |
|---|---|---|---|
| pc1 | eth1 | 192.168.1.10/24 | r1 |
| r1 | eth1 | 192.168.1.1/24 | pc1 |
| r1 | eth2 | 10.0.12.1/30 | r2 |
| r2 | eth1 | 10.0.12.2/30 | r1 |
| r2 | eth2 | 10.0.23.1/30 | r3 |
| r3 | eth1 | 10.0.23.2/30 | r2 |
| r3 | eth2 | 192.168.3.1/24 | pc2 |
| pc2 | eth1 | 192.168.3.10/24 | r3 |

Every device also has `eth0` on Containerlab's **management network**, `172.20.20.0/24`. It works like an out-of-band management port: lab traffic never uses it.

### Routing design

| Router | Role | Routes |
|---|---|---|
| r1 | Stub: one way out | Default route `0.0.0.0/0` via r2 |
| r2 | Transit: in the middle | A specific route to each LAN, and **no** default route |
| r3 | Stub: one way out | Default route `0.0.0.0/0` via r2 |

---

## Following along?

- I ran every command in a **Debian** terminal on WSL2, inside `~/network-automation-labs/lab-01-static-routing`, unless a step says PowerShell.
- Lines inside a router's command line (after `docker exec -it ... vtysh`) are shown in boxes without a language label.
- Each command is in its own box. Run **one line at a time**.
- Boxes marked **What I saw** show my output. They are not commands to run.
- Timings in the routing tables will differ on your machine.

---

## The files

### `lab01.clab.yml`

```yaml
# Lab 01: three routers in a line, a PC at each end, static routing only
name: lab01

topology:
  groups:
    routers:
      kind: frr
      image: quay.io/frrouting/frr:containerlab-10.7.1
      # Static routes only. zebra and staticd always run, so no routing
      # protocol daemons are started
      daemons:
        - staticd
    pcs:
      kind: linux
      image: wbitt/network-multitool:3.22.2

  nodes:
    r1:
      group: routers
      startup-config: r1/frr.conf
    r2:
      group: routers
      startup-config: r2/frr.conf
    r3:
      group: routers
      startup-config: r3/frr.conf
    pc1:
      group: pcs
      exec:
        - ip link set eth1 up
        - ip addr add 192.168.1.10/24 dev eth1
        # Every lab network is reached through r1. eth0 stays for management
        - ip route add 192.168.0.0/16 via 192.168.1.1 dev eth1
    pc2:
      group: pcs
      exec:
        - ip link set eth1 up
        - ip addr add 192.168.3.10/24 dev eth1
        - ip route add 192.168.0.0/16 via 192.168.3.1 dev eth1

  links:
    - endpoints: ["pc1:eth1", "r1:eth1"]
    - endpoints: ["r1:eth2", "r2:eth1"]
    - endpoints: ["r2:eth2", "r3:eth1"]
    - endpoints: ["r3:eth2", "pc2:eth1"]
```

| Part | Why |
|---|---|
| `kind: frr` | Containerlab's native FRR support, added in release 0.80. It writes each router's configuration files and enables IP forwarding |
| `image: quay.io/frrouting/frr:containerlab-10.7.1` | FRR's image made for Containerlab. It removes the management network's default route, so a router with no route drops the packet, as a real router would, instead of sending it out of the management port |
| `daemons: [staticd]` | Starts no routing protocols. `zebra` (the routing table) and `staticd` (static routes) always run |
| `startup-config` | Each router's configuration file in this repository |
| `exec` on the PCs | Gives each PC its address and a route to `192.168.0.0/16` through its router |

### Router configurations

I started with interface addresses only, no routes. After configuring the routes by hand, I saved each router's configuration and copied it back into the repository ([Step 6](#step-6-saved-the-configurations-into-the-repository)). The final `r2/frr.conf`:

```
frr version 10.7.1_git
frr defaults traditional
hostname r2
domainname localdomain
no ipv6 forwarding
service integrated-vtysh-config
!
ip route 192.168.1.0/24 10.0.12.1
ip route 192.168.3.0/24 10.0.23.2
!
interface eth1
 description Link to r1
 ip address 10.0.12.2/30
exit
!
interface eth2
 description Link to r3
 ip address 10.0.23.1/30
exit
!
```

`r1/frr.conf` and `r3/frr.conf` follow the same pattern, each with one default route.

---

## How I built it

### Step 1: Built the network

```bash
clab deploy -t lab01.clab.yml
```

**What I saw** (shortened):

```
INFO Pulling images
✔ Pulled image docker.io/wbitt/network-multitool:3.22.2
✔ Pulled image quay.io/frrouting/frr:containerlab-10.7.1
INFO Created link: pc1:eth1 ▪┄┄▪ r1:eth1
INFO Created link: r1:eth2 ▪┄┄▪ r2:eth1
INFO Created link: r2:eth2 ▪┄┄▪ r3:eth1
INFO Created link: r3:eth2 ▪┄┄▪ pc2:eth1
│ clab-lab01-pc1 │ linux │ running │ 172.20.20.2 │
│ clab-lab01-pc2 │ linux │ running │ 172.20.20.3 │
│ clab-lab01-r1  │ frr   │ running │ 172.20.20.4 │
│ clab-lab01-r2  │ frr   │ running │ 172.20.20.5 │
│ clab-lab01-r3  │ frr   │ running │ 172.20.20.6 │
```

---

## Tests I carried out

### Test 1: No routes

```bash
docker exec clab-lab01-pc1 ping -c 3 192.168.3.10
```

**What I saw:**

```
From 192.168.1.1 icmp_seq=1 Destination Net Unreachable
From 192.168.1.1 icmp_seq=2 Destination Net Unreachable
From 192.168.1.1 icmp_seq=3 Destination Net Unreachable

3 packets transmitted, 0 received, +3 errors, 100% packet loss
```

```bash
docker exec clab-lab01-r1 vtysh -c "show ip route"
```

**What I saw:**

```
C>* 10.0.12.0/30 is directly connected, eth2, weight 1, 00:00:26
L>* 10.0.12.1/32 is directly connected, eth2, weight 1, 00:00:26
C>* 172.20.20.0/24 is directly connected, eth0, weight 1, 00:00:26
L>* 172.20.20.4/32 is directly connected, eth0, weight 1, 00:00:26
C>* 192.168.1.0/24 is directly connected, eth1, weight 1, 00:00:26
L>* 192.168.1.1/32 is directly connected, eth1, weight 1, 00:00:26
```

r1 knew only its directly connected networks (`C`) and its own addresses (`L`, a /32 for each interface address, as in Cisco IOS 15). With no route to `192.168.3.0/24` and no default route, it dropped the packet and sent pc1 an **ICMP Destination Net Unreachable**, which is why every reply came from `192.168.1.1`.

### Step 2: Gave r1 a default route

```bash
docker exec -it clab-lab01-r1 vtysh
```

```
configure terminal
```

```
ip route 0.0.0.0/0 10.0.12.2
```

```
end
```

```
show ip route
```

**What I saw** (new line):

```
S>* 0.0.0.0/0 [1/0] via 10.0.12.2, eth2, weight 1, 00:00:09
```

`[1/0]` is the administrative distance (1 for a static route, as on Cisco) and the metric. `>*` means selected and installed.

### Test 2: r1 routed, r2 did not

```bash
docker exec clab-lab01-pc1 ping -c 3 192.168.3.10
```

**What I saw:**

```
3 packets transmitted, 0 received, 100% packet loss
```

I expected `Destination Net Unreachable` from r2, but got **silence**. r2 had no route to `192.168.3.0/24`, so it dropped the packet. It then tried to tell pc1, but it had no route to `192.168.1.0/24` either, so its error message was dropped too. r2's routing table confirmed it held only connected routes:

```
C>* 10.0.12.0/30 is directly connected, eth1, weight 1, 00:03:14
L>* 10.0.12.2/32 is directly connected, eth1, weight 1, 00:03:14
C>* 10.0.23.0/30 is directly connected, eth2, weight 1, 00:03:14
L>* 10.0.23.1/32 is directly connected, eth2, weight 1, 00:03:14
C>* 172.20.20.0/24 is directly connected, eth0, weight 1, 00:03:14
L>* 172.20.20.5/32 is directly connected, eth0, weight 1, 00:03:14
```

### Step 3: Gave r2 a route towards pc2 only

```bash
docker exec -it clab-lab01-r2 vtysh
```

```
configure terminal
```

```
ip route 192.168.3.0/24 10.0.23.2
```

```
end
```

**What I saw** in `show ip route` (new line):

```
S>* 192.168.3.0/24 [1/0] via 10.0.23.2, eth2, weight 1, 00:00:08
```

### Test 3: The request arrived, the reply did not

The ping from pc1 still showed 100% loss. To find out how far it got, I captured ICMP at pc2 while a longer ping ran in the background:

```bash
docker exec -d clab-lab01-pc1 ping -c 15 192.168.3.10
```

```bash
docker exec clab-lab01-pc2 timeout 5 tcpdump -n -i eth1 icmp
```

**What I saw:**

```
20:02:25.619822 IP 192.168.1.10 > 192.168.3.10: ICMP echo request, id 16496, seq 7, length 64
20:02:25.619865 IP 192.168.3.10 > 192.168.1.10: ICMP echo reply, id 16496, seq 7, length 64
20:02:26.644087 IP 192.168.1.10 > 192.168.3.10: ICMP echo request, id 16496, seq 8, length 64
20:02:26.644131 IP 192.168.3.10 > 192.168.1.10: ICMP echo reply, id 16496, seq 8, length 64
...
8 packets captured
```

pc2 received every request and answered every one, yet pc1 received nothing. The outbound path was complete. The replies died at r3, which had no route to `192.168.1.0/24`.

### Step 4: Gave r3 a default route

```bash
docker exec -it clab-lab01-r3 vtysh
```

```
configure terminal
```

```
ip route 0.0.0.0/0 10.0.23.1
```

```
end
```

**What I saw** in `show ip route` (new line):

```
S>* 0.0.0.0/0 [1/0] via 10.0.23.1, eth1, weight 1, 00:00:07
```

### Test 4: The reply reached r2 and stopped

The ping still showed 100% loss. The reply now travelled pc2 → r3 → r2, but r2 had no route to `192.168.1.0/24` and, as a transit router, no default route.

### Step 5: Gave r2 its route back to pc1's LAN

```bash
docker exec -it clab-lab01-r2 vtysh
```

```
configure terminal
```

```
ip route 192.168.1.0/24 10.0.12.1
```

```
end
```

### Test 5: End to end

```bash
docker exec clab-lab01-pc1 ping -c 3 192.168.3.10
```

**What I saw:**

```
64 bytes from 192.168.3.10: icmp_seq=1 ttl=61 time=1.05 ms
64 bytes from 192.168.3.10: icmp_seq=2 ttl=61 time=0.121 ms
64 bytes from 192.168.3.10: icmp_seq=3 ttl=61 time=0.088 ms

3 packets transmitted, 3 received, 0% packet loss
```

- `ttl=61`: pc2 sent the reply with a TTL of 64, and each of the three routers took off one.
- The first reply was slower because each hop had to resolve its neighbour's MAC address with ARP.

### Test 6: The path

```bash
docker exec clab-lab01-pc1 traceroute -n 192.168.3.10
```

**What I saw:**

```
 1  192.168.1.1  0.062 ms  0.006 ms  0.005 ms
 2  10.0.12.2  0.008 ms  0.005 ms  0.006 ms
 3  10.0.23.2  0.004 ms  0.008 ms  0.006 ms
 4  192.168.3.10  0.005 ms  0.005 ms  0.006 ms
```

Each router answered from the interface the packet **arrived on**, the side facing pc1.

### Test 7: A link failure

I shut down r2's link to r3:

```bash
docker exec -it clab-lab01-r2 vtysh
```

```
configure terminal
```

```
interface eth2
```

```
shutdown
```

```
end
```

**What I saw** in r2's `show ip route`:

```
C>* 10.0.12.0/30 is directly connected, eth1, weight 1, 01:20:02
L>* 10.0.12.2/32 is directly connected, eth1, weight 1, 01:20:02
C>* 172.20.20.0/24 is directly connected, eth0, weight 1, 01:20:02
L>* 172.20.20.5/32 is directly connected, eth0, weight 1, 01:20:02
S>* 192.168.1.0/24 [1/0] via 10.0.12.1, eth1, weight 1, 00:01:24
```

The connected route `10.0.23.0/30` disappeared with the interface. The static route to `192.168.3.0/24` disappeared too, because its next hop `10.0.23.2` was no longer reachable. It stayed in the configuration and came back when the link did.

```bash
docker exec clab-lab01-pc1 ping -c 3 192.168.3.10
```

**What I saw:**

```
From 10.0.12.2 icmp_seq=1 Destination Net Unreachable
From 10.0.12.2 icmp_seq=2 Destination Net Unreachable
From 10.0.12.2 icmp_seq=3 Destination Net Unreachable
```

Unlike Test 2, this time pc1 got an error, from r2 (`10.0.12.2`). r2 now had a route back to pc1, so its error message could be delivered. After `no shutdown` on `eth2`, the ping succeeded again.

### Step 6: Saved the configurations into the repository

FRR's equivalent of `copy running-config startup-config`, for each router:

```bash
docker exec clab-lab01-r1 vtysh -c "write memory"
```

```bash
docker exec clab-lab01-r2 vtysh -c "write memory"
```

```bash
docker exec clab-lab01-r3 vtysh -c "write memory"
```

**What I saw** (for each):

```
Note: this version of vtysh never writes vtysh.conf
Building Configuration...
Integrated configuration saved to /etc/frr/frr.conf
[OK]
```

Containerlab keeps each saved configuration in the lab folder. I compared r2's with the repository version:

```bash
diff r2/frr.conf clab-lab01/r2/config/frr.conf
```

**What I saw** (shortened):

```
> ip route 192.168.1.0/24 10.0.12.1
> ip route 192.168.3.0/24 10.0.23.2
```

FRR also rewrote the file in its own standard form, adding lines such as `service integrated-vtysh-config` and an `exit` after each interface block. I copied the saved files over the originals:

```bash
cp clab-lab01/r1/config/frr.conf r1/frr.conf
```

```bash
cp clab-lab01/r2/config/frr.conf r2/frr.conf
```

```bash
cp clab-lab01/r3/config/frr.conf r3/frr.conf
```

### Test 8: Rebuilt from the repository

I destroyed the lab, including its saved configurations, and built it again from the repository's files alone:

```bash
clab destroy -t lab01.clab.yml --cleanup
```

```bash
clab deploy -t lab01.clab.yml
```

```bash
docker exec clab-lab01-pc1 ping -c 3 192.168.3.10
```

**What I saw:**

```
64 bytes from 192.168.3.10: icmp_seq=1 ttl=61 time=4.90 ms
64 bytes from 192.168.3.10: icmp_seq=2 ttl=61 time=0.145 ms
64 bytes from 192.168.3.10: icmp_seq=3 ttl=61 time=0.117 ms

3 packets transmitted, 3 received, 0% packet loss
```

It worked first time, with nothing typed on any router. The repository fully describes the working network.

| Test | Expected | Result |
|---|---|---|
| 1. No routes | Unreachable from r1 | ✅ |
| 2. r1 only | Fails at r2, silently | ✅ |
| 3. r1 and r2 outbound | Request reaches pc2, reply lost | ✅ |
| 4. Plus r3 | Reply lost at r2 | ✅ |
| 5. All routes | 0% loss, TTL 61 | ✅ |
| 6. Traceroute | Three routers, then pc2 | ✅ |
| 7. Link down | Static route withdrawn, unreachable from r2, recovers after `no shutdown` | ✅ |
| 8. Rebuild | Works with no manual configuration | ✅ |

---

## Issues I hit and how I fixed them

### 1. `code .` failed with "Exec format error"

**Symptom.** Running `code .` in Debian to open VS Code failed:

```
/mnt/c/Users/<user>/AppData/Local/Programs/Microsoft VS Code/Code.exe: Exec format error
```

**Root cause.** WSL starts Windows programs from Linux through a feature called interop. Containerlab's setup enabled systemd in Debian so Docker can run as a service, and on some systems systemd removes the interop setting. Linux then tries to run `Code.exe` as a Linux program. This is a known WSL issue.

**Fix.** I opened VS Code on Windows instead, installed the **WSL** extension, and used **WSL: Connect to WSL using Distro** to connect to Debian. That route does not need interop. The same issue meant `gh auth login` could not open a browser, so I opened the device login page myself.

### 2. VS Code created the files inside each other

**Symptom.** `ls -R` before deploying showed each router's folder nested inside an extra `lab-01-static-routing` folder, inside the previous router's folder.

**Root cause.** VS Code's **New File** creates the typed path inside whichever folder is selected in the Explorer. After the first file, the lab folder stayed selected, so each full path was added inside it again.

**Fix.** I moved the folders up with `mv`, deepest first, then removed the empty folders with `rmdir`, which only deletes empty folders. Now I click an empty part of the Explorer before creating a file.

**Lesson.** Listing the folder before deploying caught this before it could cause a confusing error.

### 3. The first packet capture was empty

**Symptom.** `tcpdump` reported `0 packets captured`.

**Root cause.** A 4-packet ping finishes in about 3 seconds, which had passed before I started the capture.

**Fix.** A 15-packet ping in the background left enough time to start capturing.

### Note: "Configuration applied with notes: No changes found to be committed!"

FRR 10 printed this when I entered `interface eth2`. It is not an error: entering an interface's configuration mode changes nothing by itself, and FRR's management daemon reports that.

---

## Clean-up

```bash
clab destroy -t lab01.clab.yml --cleanup
```

`--cleanup` also removes the lab folder `clab-lab01`, including any configurations saved there, so copy them into the repository first.

---

## Command reference

| Command | What it does |
|---|---|
| `clab deploy -t <file>` | Builds the network described in the topology file |
| `clab destroy -t <file> --cleanup` | Removes the network and its lab folder |
| `docker exec -it <node> vtysh` | Opens a router's command line |
| `docker exec <node> vtysh -c "<command>"` | Runs one router command without opening the command line |
| `show ip route` | Shows the routing table |
| `ip route <network> <next hop>` | Adds a static route (in configuration mode) |
| `shutdown` / `no shutdown` | Disables or enables an interface (in interface mode) |
| `write memory` | Saves the running configuration |
| `docker exec <pc> ping -c 3 <address>` | Sends three pings from a PC |
| `docker exec <pc> traceroute -n <address>` | Shows each router on the path |
| `docker exec <pc> tcpdump -n -i eth1 icmp` | Captures ICMP packets on an interface |

## What I learned

- A router only knows its connected networks until it is told about others, by static routes or a routing protocol.
- Routing is hop by hop: every router on the path needs a route in **both** directions.
- "Destination Net Unreachable" names the router that gave up. **Silence** often means the error itself had no way back, which points to a return-path problem.
- A packet capture at the destination separates "the request never arrived" from "the reply never got back".
- Stub routers suit a default route. A transit router needs specific routes, so it does not send unknown traffic the wrong way.
- A static route is withdrawn when its next hop becomes unreachable, and returns automatically when it recovers.
- The TTL in a reply shows how many routers it crossed.
- Saving the running configuration back into the repository and rebuilding from it proves the repository is complete.

---

## References

Official documentation I used while building and testing this lab.

| What I did | Documentation |
|---|---|
| Installed Containerlab on Windows | [Containerlab: Windows](https://containerlab.dev/windows/) |
| Ran the routers with the `frr` kind | [Containerlab: FRRouting kind](https://containerlab.dev/manual/kinds/frr/) |
| Ran the PCs | [Containerlab: Linux kind](https://containerlab.dev/manual/kinds/linux/) |
| Destroyed the lab and its folder | [Containerlab: destroy command](https://containerlab.dev/cmd/destroy) |
| Configured static routes | [FRR: STATIC](https://docs.frrouting.org/en/stable-10.7/static.html) |
| Worked around the interop error | [WSL issue 8952](https://github.com/microsoft/WSL/issues/8952) |
| Opened the files in VS Code | [VS Code: Developing in WSL](https://code.visualstudio.com/docs/remote/wsl) |
| Signed in to GitHub from Debian | [GitHub CLI: gh auth login](https://cli.github.com/manual/gh_auth_login) |