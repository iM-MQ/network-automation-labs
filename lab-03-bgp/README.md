# Lab 03: BGP Between Two Companies

## Overview

| | |
|---|---|
| **Goal** | Connect two separate organisations, each running OSPF inside, with eBGP between their edge routers. Control exactly which networks cross with prefix lists and route maps, then redistribute the result into each company's OSPF |
| **Runs on** | Containerlab and FRRouting 10.7.1, in Debian on WSL2 |
| **Cost** | Free. Everything runs on my computer |
| **Time** | About three hours |

OSPF runs **inside** an organisation. Between organisations, such as two companies, or a company and its internet provider, routes are exchanged with **BGP**. Each organisation is an **autonomous system (AS)** with its own number, and shares only the routes it chooses.

The most useful finding: when the BGP session first came up, **no routes crossed it at all**. FRR follows RFC 8212, which forbids exchanging eBGP routes until an explicit policy exists in both directions. Writing that policy became the core of the lab.

---

## Topology

```
        Company A (AS 65001)                       Company B (AS 65002)
 ┌───────────────────────────────┐      ┌───────────────────────────────┐
 │ pc1 ── r1 ──────────── r2 ────┼─eBGP─┼──── r3 ──────────── r4 ── pc2 │
 │  .10  .1   10.0.12.0/30   .1  │ .1 .2│  .1   10.0.34.0/30   .1  .10 │
 │ 192.168.1.0/24                │10.0.23.0/30               192.168.4.0/24
 │        OSPF area 0            │      │         OSPF area 0           │
 └───────────────────────────────┘      └───────────────────────────────┘
   loopbacks: r1 1.1.1.1  r2 2.2.2.2       r3 3.3.3.3  r4 4.4.4.4
```

| Router | Company | Interface | Address | Connects to |
|---|---|---|---|---|
| r1 | A (65001) | eth1 | 192.168.1.1/24 | pc1 |
| r1 | A | eth2 | 10.0.12.1/30 | r2 |
| r2 | A | eth1 | 10.0.12.2/30 | r1 |
| r2 | A | eth2 | 10.0.23.1/30 | r3, the **eBGP link** |
| r3 | B (65002) | eth1 | 10.0.23.2/30 | r2, the **eBGP link** |
| r3 | B | eth2 | 10.0.34.1/30 | r4 |
| r4 | B | eth1 | 10.0.34.2/30 | r3 |
| r4 | B | eth2 | 192.168.4.1/24 | pc2 |

The eBGP link, `10.0.23.0/30`, is deliberately in **neither** company's OSPF. Companies do not run their internal routing protocol with each other; only BGP crosses that link.

### What each company shares

| Company | Advertises | Accepts from the other |
|---|---|---|
| A (r2) | `192.168.1.0/24` (LAN), `1.1.1.1/32` (loopback) | `192.168.4.0/24`, `4.4.4.4/32` |
| B (r3) | `192.168.4.0/24` (LAN), `4.4.4.4/32` (loopback) | `192.168.1.0/24` **only**. A's loopback is refused on purpose |

---

## Following along?

- I ran every command in a **Debian** terminal on WSL2, inside `~/network-automation-labs/lab-03-bgp`.
- Lines typed inside a router's command line (after `docker exec -it ... vtysh`) are shown in boxes without a language label.
- Each command is in its own box. Run **one line at a time**.
- Boxes marked **What I saw** show my output. They are not commands to run.
- Up-times and table versions will differ on your machine.

---

## The files

### `lab03.clab.yml`

```yaml
# Lab 03: two companies, each running OSPF inside, connected by eBGP
name: lab03

topology:
  groups:
    routers:
      kind: frr
      image: quay.io/frrouting/frr:containerlab-10.7.1
      # OSPF inside each company, BGP between them
      daemons:
        - ospfd
        - bgpd
    pcs:
      kind: linux
      image: wbitt/network-multitool:3.22.2

  nodes:
    # Company A, AS 65001
    r1:
      group: routers
      startup-config: r1/frr.conf
    r2:
      group: routers
      startup-config: r2/frr.conf
    # Company B, AS 65002
    r3:
      group: routers
      startup-config: r3/frr.conf
    r4:
      group: routers
      startup-config: r4/frr.conf
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
        - ip addr add 192.168.4.10/24 dev eth1
        - ip route add 192.168.0.0/16 via 192.168.4.1 dev eth1

  links:
    - endpoints: ["pc1:eth1", "r1:eth1"]
    - endpoints: ["r1:eth2", "r2:eth1"]
    # The link between the two companies, where eBGP runs
    - endpoints: ["r2:eth2", "r3:eth1"]
    - endpoints: ["r3:eth2", "r4:eth1"]
    - endpoints: ["r4:eth2", "pc2:eth1"]
```

### Router configurations

OSPF inside each company was in the startup configurations from the start, since I configured OSPF by hand in [Lab 02](../lab-02-ospf). I configured BGP, the filters and redistribution by hand, then saved them back into the repository ([Step 4](#step-4-saved-the-configurations-into-the-repository)). The parts I added to r3, Company B's edge router:

```
ip prefix-list COMPANY-B-OUT seq 10 permit 192.168.4.0/24
ip prefix-list COMPANY-B-OUT seq 20 permit 4.4.4.4/32
ip prefix-list COMPANY-A-IN seq 10 permit 192.168.1.0/24
!
route-map TO-COMPANY-A permit 10
 match ip address prefix-list COMPANY-B-OUT
exit
!
route-map FROM-COMPANY-A permit 10
 match ip address prefix-list COMPANY-A-IN
exit
!
router bgp 65002
 bgp router-id 3.3.3.3
 neighbor 10.0.23.1 remote-as 65001
 !
 address-family ipv4 unicast
  network 4.4.4.4/32
  network 192.168.4.0/24
  neighbor 10.0.23.1 soft-reconfiguration inbound
  neighbor 10.0.23.1 route-map FROM-COMPANY-A in
  neighbor 10.0.23.1 route-map TO-COMPANY-A out
 exit-address-family
exit
!
router ospf
 ospf router-id 3.3.3.3
 redistribute bgp
 network 3.3.3.3/32 area 0
 network 10.0.34.0/30 area 0
exit
```

r2 mirrors it for Company A, with `COMPANY-B-IN` permitting both of Company B's networks.

| Part | What it does |
|---|---|
| `router bgp 65002` | Runs BGP as AS 65002 |
| `neighbor 10.0.23.1 remote-as 65001` | A neighbour in a **different** AS, so this is external BGP (eBGP) |
| `network 192.168.4.0/24` | Advertises this network, but **only if that exact route is already in the routing table**. Unlike OSPF's `network`, it does not turn anything on for an interface |
| `ip prefix-list` | Lists which networks match. Anything not listed is denied |
| `route-map ... permit 10` / `match ip address prefix-list` | Permits routes matching the list. Anything not matched is denied |
| `neighbor ... route-map ... in` / `out` | Applies a policy to routes received from, or sent to, the neighbour |
| `soft-reconfiguration inbound` | Keeps a copy of every route received, including ones the policy rejects, so I can see what was filtered |
| `redistribute bgp` (under `router ospf`) | Passes routes learnt by BGP into OSPF, so routers that only run OSPF learn them too |

---

## How I built it

### Step 1: Built the network with OSPF only

```bash
clab deploy -t lab03.clab.yml
```

```bash
docker exec clab-lab03-r2 vtysh -c "show ip route ospf"
```

**What I saw:**

```
O>* 1.1.1.1/32 [110/10] via 10.0.12.1, eth1, weight 1, 00:00:32
O>* 192.168.1.0/24 [110/20] via 10.0.12.1, eth1, weight 1, 00:00:32
```

r2 knew Company A's networks through OSPF, and nothing beyond its directly connected link to Company B. A ping from pc1 to pc2 stopped at r1:

```
From 192.168.1.1 icmp_seq=1 Destination Net Unreachable
```

### Step 2: Brought up eBGP between r2 and r3

On r2:

```bash
docker exec -it clab-lab03-r2 vtysh
```

```
configure terminal
```

```
router bgp 65001
```

```
bgp router-id 2.2.2.2
```

```
neighbor 10.0.23.2 remote-as 65002
```

```
address-family ipv4 unicast
```

```
network 192.168.1.0/24
```

```
network 1.1.1.1/32
```

```
exit-address-family
```

```
end
```

r3 was the mirror image: `router bgp 65002`, router ID `3.3.3.3`, `neighbor 10.0.23.1 remote-as 65001`, and the networks `192.168.4.0/24` and `4.4.4.4/32`.

### Step 3: Wrote the policies

On r2, Company A advertises its two networks and accepts both of Company B's:

```
ip prefix-list COMPANY-A-OUT seq 10 permit 192.168.1.0/24
```

```
ip prefix-list COMPANY-A-OUT seq 20 permit 1.1.1.1/32
```

```
ip prefix-list COMPANY-B-IN seq 10 permit 192.168.4.0/24
```

```
ip prefix-list COMPANY-B-IN seq 20 permit 4.4.4.4/32
```

```
route-map TO-COMPANY-B permit 10
```

```
match ip address prefix-list COMPANY-A-OUT
```

```
exit
```

```
route-map FROM-COMPANY-B permit 10
```

```
match ip address prefix-list COMPANY-B-IN
```

```
exit
```

```
router bgp 65001
```

```
address-family ipv4 unicast
```

```
neighbor 10.0.23.2 route-map FROM-COMPANY-B in
```

```
neighbor 10.0.23.2 route-map TO-COMPANY-B out
```

```
end
```

On r3, the same pattern, except `COMPANY-A-IN` permits **only** `192.168.1.0/24`, and I added `neighbor 10.0.23.1 soft-reconfiguration inbound`. Then I asked each router to resend its routes under the new policies, without dropping the session:

```bash
docker exec clab-lab03-r2 vtysh -c "clear bgp ipv4 unicast 10.0.23.2 soft"
```

```bash
docker exec clab-lab03-r3 vtysh -c "clear bgp ipv4 unicast 10.0.23.1 soft"
```

Finally, on each edge router, I redistributed BGP into OSPF:

```bash
docker exec clab-lab03-r2 vtysh -c "configure terminal" -c "router ospf" -c "redistribute bgp"
```

```bash
docker exec clab-lab03-r3 vtysh -c "configure terminal" -c "router ospf" -c "redistribute bgp"
```

---

## Tests I carried out

### Test 1: The session was up, but no routes crossed it

Before writing any policy:

```bash
docker exec clab-lab03-r2 vtysh -c "show bgp summary"
```

**What I saw:**

```
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.23.2       4      65002         3         4        2    0    0 00:00:19     (Policy) (Policy) N/A
```

The session had been up for 19 seconds and messages were flowing, but `(Policy)` appeared where the received and sent route counts should be. FRR's defaults follow **RFC 8212**: over eBGP, a router accepts and advertises nothing until a policy exists for the neighbour in both directions. It prevents the classic outage where one network accidentally advertises routes it should not, and its neighbour accepts them blindly.

r2's BGP table held only its own networks:

```
     Network          Next Hop            Metric LocPrf Weight Path
 *>  1.1.1.1/32       0.0.0.0                  0         32768 i
 *>  192.168.1.0/24   0.0.0.0                  0         32768 i
```

Next hop `0.0.0.0` and weight `32768` mark routes this router originates itself.

### Test 2: Routes crossed, and the filter removed one

After the policies:

```bash
docker exec clab-lab03-r2 vtysh -c "show bgp summary"
```

**What I saw:**

```
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.23.2       4      65002        14        16        4    0    0 00:03:40            2        2 N/A
```

```bash
docker exec clab-lab03-r3 vtysh -c "show bgp summary"
```

**What I saw:**

```
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.23.1       4      65001        15        14        3    0    0 00:03:43            1        2 N/A
```

r2 received 2 and sent 2. r3 sent 2 but **kept only 1**. What r3 received before filtering:

```bash
docker exec clab-lab03-r3 vtysh -c "show bgp ipv4 unicast neighbors 10.0.23.1 received-routes"
```

**What I saw:**

```
     Network          Next Hop            Metric LocPrf Weight Path
 *> 1.1.1.1/32       10.0.23.1                0             0 65001 i
 *> 192.168.1.0/24   10.0.23.1                0             0 65001 i

Total number of prefixes 2 (1 filtered)
```

And what it kept:

```bash
docker exec clab-lab03-r3 vtysh -c "show bgp ipv4 unicast"
```

**What I saw:**

```
     Network          Next Hop            Metric LocPrf Weight Path
 *>  4.4.4.4/32       0.0.0.0                  0         32768 i
 *>  192.168.1.0/24   10.0.23.1                0             0 65001 i
 *>  192.168.4.0/24   0.0.0.0                  0         32768 i
```

r2 sent `1.1.1.1/32`, and r3's inbound filter dropped it. `soft-reconfiguration inbound` is what made the rejected route visible, which is the evidence I would want in an audit or a troubleshooting call.

**The AS path, `65001`,** records the autonomous systems a route has crossed. BGP uses it to prevent loops, by rejecting any route whose path already contains its own AS, and as a tie-breaker, preferring the shortest path.

### Test 3: BGP alone was not enough

r2 learnt Company B's networks:

```bash
docker exec clab-lab03-r2 vtysh -c "show ip route bgp"
```

**What I saw:**

```
B>* 4.4.4.4/32 [20/0] via 10.0.23.2, eth2, weight 1, 00:01:10
B>* 192.168.4.0/24 [20/0] via 10.0.23.2, eth2, weight 1, 00:01:10
```

`20` is eBGP's administrative distance, as on Cisco. Yet pc1 still could not reach pc2, and the unreachable message still came from r1, because r1 does not run BGP and its OSPF table held only r2's loopback:

```
O>* 2.2.2.2/32 [110/10] via 10.0.12.2, eth2, weight 1, 00:06:14
```

Routes learnt by one protocol stay in that protocol unless they are **redistributed**.

### Test 4: Redistribution joined the two companies

After `redistribute bgp` on both edge routers:

```bash
docker exec clab-lab03-r1 vtysh -c "show ip ospf route"
```

**What I saw** (shortened):

```
============ OSPF router routing table =============
R    2.2.2.2               [10] area: 0.0.0.0, ASBR
                           via 10.0.12.2, eth2

============ OSPF external routing table ===========
N E2 4.4.4.4/32            [10/20] tag: 0
                           via 10.0.12.2, eth2
N E2 192.168.4.0/24        [10/20] tag: 0
                           via 10.0.12.2, eth2
```

- **r2 became an ASBR** (Autonomous System Boundary Router), a router that injects routes from outside OSPF.
- **Company B's networks arrived as external type 2 (`E2`) routes.** `[10/20]` is the cost to the ASBR (10) and the external metric (20, FRR's default). OSPF compares E2 routes on the external metric alone, which is why r1's routing table showed `[110/20]` rather than 30. Type 1 (`E1`) routes would add the two.

```bash
docker exec clab-lab03-pc1 ping -c 3 192.168.4.10
```

**What I saw:**

```
64 bytes from 192.168.4.10: icmp_seq=1 ttl=60 time=4.74 ms
64 bytes from 192.168.4.10: icmp_seq=2 ttl=60 time=0.114 ms
64 bytes from 192.168.4.10: icmp_seq=3 ttl=60 time=0.197 ms
```

```bash
docker exec clab-lab03-pc1 traceroute -n 192.168.4.10
```

**What I saw:**

```
 1  192.168.1.1  0.095 ms  0.008 ms  0.008 ms
 2  10.0.12.2  0.015 ms  0.010 ms  0.024 ms
 3  10.0.23.2  0.009 ms  0.008 ms  0.012 ms
 4  10.0.34.2  0.007 ms  0.010 ms  0.006 ms
 5  192.168.4.10  0.011 ms  0.007 ms  0.007 ms
```

`ttl=60` means four routers. The path crossed both companies, and the replies from r3 and r4 prove Company B also knew the way back.

### Test 5: The filter had real consequences

From r4, inside Company B:

```bash
docker exec clab-lab03-r4 ping -c 2 1.1.1.1
```

**What I saw:**

```
ping: sendto: Network unreachable
```

r3 refused `1.1.1.1/32`, so Company B had no route to it at all, and the ping failed before sending a packet. Company A's LAN was reachable, once I chose the right source address ([Issue 1](#1-a-ping-from-r4-to-company-as-lan-failed)):

```bash
docker exec clab-lab03-r4 ping -c 2 -I 192.168.4.1 192.168.1.1
```

**What I saw:**

```
64 bytes from 192.168.1.1: seq=0 ttl=62 time=3.748 ms
64 bytes from 192.168.1.1: seq=1 ttl=62 time=0.157 ms
```

### Test 6: The link between the companies failed

```bash
docker exec clab-lab03-r2 vtysh -c "configure terminal" -c "interface eth2" -c "shutdown"
```

```bash
docker exec clab-lab03-r2 vtysh -c "show bgp summary"
```

**What I saw:**

```
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.23.2       4      65002        18        20        0    0    0 00:00:04       Active        0 N/A
```

`Active` means trying to connect, so the session was down. FRR noticed at once because the interface went down, rather than waiting for BGP's hold timer. Within seconds r1 had lost the redistributed routes, and pc1's ping failed at r1 again:

```
From 192.168.1.1 icmp_seq=1 Destination Net Unreachable
```

After `no shutdown`, the session was back with `2` received and `2` sent by my next check, 5 seconds later, and the ping worked again.

### Step 4: Saved the configurations into the repository

```bash
docker exec clab-lab03-r1 vtysh -c "write memory"
```

```bash
docker exec clab-lab03-r2 vtysh -c "write memory"
```

```bash
docker exec clab-lab03-r3 vtysh -c "write memory"
```

```bash
docker exec clab-lab03-r4 vtysh -c "write memory"
```

I checked r2's saved file had no leftover `shutdown` from Test 6:

```bash
grep -n "shutdown" clab-lab03/r2/config/frr.conf
```

It printed nothing. I copied each saved file over its original:

```bash
cp clab-lab03/r1/config/frr.conf r1/frr.conf
```

```bash
cp clab-lab03/r2/config/frr.conf r2/frr.conf
```

```bash
cp clab-lab03/r3/config/frr.conf r3/frr.conf
```

```bash
cp clab-lab03/r4/config/frr.conf r4/frr.conf
```

### Test 7: Rebuilt from the repository

```bash
clab destroy -t lab03.clab.yml --cleanup
```

```bash
clab deploy -t lab03.clab.yml
```

```bash
docker exec clab-lab03-r3 vtysh -c "show bgp summary"
```

**What I saw** 15 seconds after deploying:

```
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.23.1       4      65001         4         5        0    0    0 00:00:15            0        0 N/A
```

**And a few minutes later:**

```
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.23.1       4      65001         9        11        3    0    0 00:04:54            1        2 N/A
```

```bash
docker exec clab-lab03-pc1 ping -c 3 192.168.4.10
```

**What I saw:**

```
64 bytes from 192.168.4.10: icmp_seq=1 ttl=60 time=2.13 ms
64 bytes from 192.168.4.10: icmp_seq=2 ttl=60 time=0.074 ms
64 bytes from 192.168.4.10: icmp_seq=3 ttl=60 time=0.078 ms
```

The rebuilt network worked with no manual configuration, and the filter was back (`1` received). The early check showed something useful: the BGP session was up within seconds, but **empty**. Each edge router advertises networks it learns through OSPF, and BGP's `network` command only advertises a route once it is in the routing table. Until OSPF converged inside each company, there was nothing to send. Here, BGP depends on OSPF.

| Test | Expected | Result |
|---|---|---|
| 1. No policy | Session up, `(Policy)`, no routes exchanged | ✅ |
| 2. Policies | r2 2/2, r3 1/2, `1 filtered` | ✅ |
| 3. BGP only | r2 learns B's networks, r1 does not | ✅ |
| 4. Redistribution | `E2` routes on r1, end-to-end ping with `ttl=60` | ✅ |
| 5. Filter | `1.1.1.1/32` unreachable from Company B | ✅ |
| 6. Link failure | Session down at once, routes withdrawn, recovered after `no shutdown` | ✅ |
| 7. Rebuild | Works with no manual configuration | ✅ |

---

## Issues I hit and how I fixed them

### 1. A ping from r4 to Company A's LAN failed

**Symptom.** `ping -c 2 192.168.1.1` from r4 showed 100% loss with no error, even though r4 had a route to `192.168.1.0/24`.

**Root cause.** A router pings from the address of the interface the packet leaves by, here `10.0.34.2`. The request reached r1, but Company B never advertised `10.0.34.0/30`, so Company A had no route back. The same return-path problem as [Lab 01](../lab-01-static-routing).

**Fix.** `-I 192.168.4.1` made r4 use its LAN address, which Company A knows. Users were never affected, because their addresses are in the advertised networks.

**Lesson.** When a test from a router fails but users are fine, check the source address.

### 2. Commands ran in PowerShell instead of Debian

**Symptom.** `cd ~/network-automation-labs` failed with `Cannot find path 'C:\Users\<user>\network-automation-labs'`.

**Root cause.** VS Code was not connected to Debian, so its terminal opened PowerShell.

**Fix.** `wsl -d Debian` for the terminal, and **WSL: Connect to WSL using Distro** in VS Code before creating any files, so they were saved inside Debian.

### Note: the first routing table was too early

I first looked at r2's routing table 15 seconds after deploying, before OSPF had formed its neighbour with r1, so it showed only connected routes. A minute later the OSPF routes were there.

---

## Clean-up

```bash
clab destroy -t lab03.clab.yml --cleanup
```

---

## Command reference

| Command | What it does |
|---|---|
| `router bgp <asn>` | Enters BGP configuration for an autonomous system |
| `neighbor <ip> remote-as <asn>` | Defines a BGP neighbour. A different AS makes it eBGP |
| `network <prefix>` (in `address-family ipv4 unicast`) | Advertises a network that is already in the routing table |
| `ip prefix-list <name> seq <n> permit <prefix>` | Lists networks to match |
| `route-map <name> permit <n>` / `match ip address prefix-list <name>` | Builds a policy from a prefix list |
| `neighbor <ip> route-map <name> in\|out` | Applies a policy to a neighbour |
| `neighbor <ip> soft-reconfiguration inbound` | Keeps every received route, including filtered ones |
| `clear bgp ipv4 unicast <ip> soft` | Resends routes under new policies without dropping the session |
| `redistribute bgp` (under `router ospf`) | Passes BGP routes into OSPF as external routes |
| `show bgp summary` | Neighbours, their state, and routes received and sent |
| `show bgp ipv4 unicast` | The BGP table, with next hops and AS paths |
| `show bgp ipv4 unicast neighbors <ip> received-routes` | Everything a neighbour sent, before filtering |
| `show ip route bgp` | BGP routes installed in the routing table |
| `show ip ospf route` | OSPF's view, including external (`E1`/`E2`) routes and ASBRs |
| `ping -I <source> <destination>` | Pings from a chosen source address |

## What I learned

- OSPF runs inside an organisation. BGP connects organisations, and each one decides exactly what to share.
- FRR follows RFC 8212: an eBGP session can be up while exchanging nothing, until there is a policy in both directions.
- Prefix lists and route maps both end with an implicit deny, so anything not listed is blocked.
- `soft-reconfiguration inbound` turns "the filter is working" into evidence I can show.
- BGP's `network` command advertises a route only if it is already in the routing table, which makes BGP depend on the IGP underneath it.
- The AS path prevents loops and is part of how BGP chooses between routes.
- Routes stay in the protocol that learnt them unless they are redistributed. Redistributed routes appear in OSPF as external `E2` routes, from an ASBR.
- Advertising only user subnets has a side effect: tests sourced from router interfaces can fail when user traffic is fine.

---

## References

Official documentation I used while building and testing this lab.

| What I did | Documentation |
|---|---|
| Configured BGP, neighbours and soft reconfiguration | [FRR 10.7.1: BGP user documentation](https://github.com/FRRouting/frr/blob/frr-10.7.1/doc/user/bgp.rst) |
| Wrote the prefix lists | [FRR 10.7.1: Filtering](https://github.com/FRRouting/frr/blob/frr-10.7.1/doc/user/filter.rst) |
| Wrote the route maps | [FRR 10.7.1: Route maps](https://github.com/FRRouting/frr/blob/frr-10.7.1/doc/user/routemap.rst) |
| Redistributed BGP into OSPF | [FRR 10.7.1: OSPFv2 user documentation](https://github.com/FRRouting/frr/blob/frr-10.7.1/doc/user/ospfd.rst) |
| Understood why no routes crossed without policy | [RFC 8212: Default EBGP Route Propagation Behavior without Policies](https://www.rfc-editor.org/rfc/rfc8212) |
| Understood the AS path and BGP's behaviour | [RFC 4271: A Border Gateway Protocol 4 (BGP-4)](https://www.rfc-editor.org/rfc/rfc4271) |
| Ran the routers with the `frr` kind | [Containerlab: FRRouting kind](https://containerlab.dev/manual/kinds/frr/) |
| Destroyed the lab and its folder | [Containerlab: destroy command](https://containerlab.dev/cmd/destroy) |