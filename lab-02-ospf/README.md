# Lab 02: OSPF

## Overview

| | |
|---|---|
| **Goal** | Replace Lab 01's static routes with OSPF, add a second path, and watch the routers find each other, elect a DR, share traffic over equal paths and reroute around a failure |
| **Runs on** | Containerlab and FRRouting 10.7.1, in Debian on WSL2 |
| **Cost** | Free. Everything runs on my computer |
| **Time** | About three hours |

In Lab 01, a failed link stopped traffic, because static routes cannot find another way. Here, with OSPF and a direct link between r1 and r3, the same failure caused **no lost pings at all**: OSPF moved traffic to the longer path within one ping interval.

---

## Topology

```
                 2.2.2.2 (lo)
                      r2
          10.0.12.0/30  ╲      10.0.23.0/30
            .1 ╱  .2     ╲ .1       .2
              ╱           ╲
 pc1 ──── r1 ───────────── r3 ──── pc2
     .10 .1  .1         .2  .1  .10
192.168.1.0/24  10.0.13.0/30  192.168.3.0/24
   1.1.1.1 (lo)               3.3.3.3 (lo)
```

| Router | Interface | Address | Connects to |
|---|---|---|---|
| r1 | eth1 | 192.168.1.1/24 | pc1 (passive in OSPF) |
| r1 | eth2 | 10.0.12.1/30 | r2 |
| r1 | eth3 | 10.0.13.1/30 | r3, the new direct link |
| r1 | lo | 1.1.1.1/32 | Loopback, used as the router ID |
| r2 | eth1 | 10.0.12.2/30 | r1 |
| r2 | eth2 | 10.0.23.1/30 | r3 |
| r2 | lo | 2.2.2.2/32 | Loopback |
| r3 | eth1 | 10.0.23.2/30 | r2 |
| r3 | eth2 | 192.168.3.1/24 | pc2 (passive in OSPF) |
| r3 | eth3 | 10.0.13.2/30 | r1, the new direct link |
| r3 | lo | 3.3.3.3/32 | Loopback |

Every router runs OSPF in **area 0**. pc1 and pc2 are set up exactly as in Lab 01.

---

## Following along?

- I ran every command in a **Debian** terminal on WSL2, inside `~/network-automation-labs/lab-02-ospf`.
- Lines typed inside a router's command line (after `docker exec -it ... vtysh`) are shown in boxes without a language label.
- Each command is in its own box. Run **one line at a time**.
- Boxes marked **What I saw** show my output. They are not commands to run.
- Timers and up-times will differ on your machine, and so may the DR election: see [Test 1](#test-1-the-dr-was-not-the-highest-router-id).

---

## The files

### `lab02.clab.yml`

The same as Lab 01, with `ospfd` started and a fifth link between r1 and r3:

```yaml
# Lab 02: three routers in a triangle, a PC at each end, OSPF single area
name: lab02

topology:
  groups:
    routers:
      kind: frr
      image: quay.io/frrouting/frr:containerlab-10.7.1
      # OSPF only. zebra and staticd always run as well
      daemons:
        - ospfd
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
    # The new link: a second path between r1 and r3
    - endpoints: ["r1:eth3", "r3:eth3"]
    - endpoints: ["r3:eth2", "pc2:eth1"]
```

### Router configurations

I started with interface and loopback addresses only, configured OSPF by hand on each router, then saved the configurations back into the repository ([Step 3](#step-3-saved-the-configurations-into-the-repository)). The OSPF part of the final `r1/frr.conf`:

```
interface eth1
 description LAN to pc1
 ip address 192.168.1.1/24
 ip ospf passive
exit
!
router ospf
 ospf router-id 1.1.1.1
 network 1.1.1.1/32 area 0
 network 10.0.12.0/30 area 0
 network 10.0.13.0/30 area 0
 network 192.168.1.0/24 area 0
exit
```

| Line | What it does |
|---|---|
| `ospf router-id 1.1.1.1` | Names the router in OSPF. I used the loopback address, because a loopback never goes down |
| `network ... area 0` | Turns on OSPF, in area 0, on every interface with an address inside that network, and advertises the network |
| `ip ospf passive` | Advertises pc1's LAN but sends no hellos on it, since no router is there to talk to. Cisco uses `passive-interface eth1` under `router ospf`. FRR documents this per-interface form |

FRR writes networks as prefixes (`10.0.12.0/30`) where Cisco uses wildcard masks (`10.0.12.0 0.0.0.3`).

---

## How I built it

### Step 1: Built the network with no routing protocol running

```bash
clab deploy -t lab02.clab.yml
```

```bash
docker exec clab-lab02-r1 vtysh -c "show ip route"
```

**What I saw** (shortened):

```
L * 1.1.1.1/32 is directly connected, lo, weight 1, 00:00:05
C>* 1.1.1.1/32 is directly connected, lo, weight 1, 00:00:05
C>* 10.0.12.0/30 is directly connected, eth2, weight 1, 00:00:05
C>* 10.0.13.0/30 is directly connected, eth3, weight 1, 00:00:05
C>* 192.168.1.0/24 is directly connected, eth1, weight 1, 00:00:05
```

Only connected networks, as in Lab 01, plus the loopback. Because the loopback is a /32, its connected and local entries are the same prefix, and FRR selects the connected one.

### Step 2: Turned on OSPF on r1, then r2, then r3

On r1:

```bash
docker exec -it clab-lab02-r1 vtysh
```

```
configure terminal
```

```
router ospf
```

```
ospf router-id 1.1.1.1
```

```
network 1.1.1.1/32 area 0
```

```
network 10.0.12.0/30 area 0
```

```
network 10.0.13.0/30 area 0
```

```
network 192.168.1.0/24 area 0
```

```
exit
```

```
interface eth1
```

```
ip ospf passive
```

```
end
```

```
show ip ospf neighbor
```

**What I saw:** an empty neighbour table. r1 was sending hellos out of eth2 and eth3, but nothing at the other end was running OSPF.

r2 followed the same pattern with router ID `2.2.2.2` and the networks `2.2.2.2/32`, `10.0.12.0/30` and `10.0.23.0/30`. It has no LAN, so no passive interface. r3 used router ID `3.3.3.3`, the networks `3.3.3.3/32`, `10.0.13.0/30`, `10.0.23.0/30` and `192.168.3.0/24`, and `ip ospf passive` on eth2.

---

## Tests I carried out

### Test 1: The DR was not the highest router ID

As soon as I enabled OSPF on r2, it formed an adjacency with r1:

```
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface
1.1.1.1           1 Full/DR         2.689s            37.307s 10.0.12.1       eth1:10.0.12.2
```

I expected r2 to become the **Designated Router (DR)**, since with equal priorities the highest router ID wins, and 2.2.2.2 is higher than 1.1.1.1. Instead r1 was DR.

**The DR election is not pre-emptive.** r1 had been alone on the link for longer than its 40-second wait timer, so it had already elected itself DR. When r2 arrived, r1's hellos announced an existing DR, and r2 accepted it rather than forcing a new election. That is also why r2 reached `Full` in under 3 seconds, with no wait.

After r3 joined, the roles were:

| Link | DR | BDR | Why |
|---|---|---|---|
| r1–r2 | r1 | r2 | r1 was there first |
| r1–r3 | r1 | r3 | r1 was there first |
| r2–r3 | r2 | r3 | r2 was there first |

r3 has the highest router ID but was DR nowhere, because it joined last. On a real network, the DR is often simply whichever router booted first. To choose the DR, set its priority, then restart OSPF.

### Test 2: The routes OSPF found

```bash
docker exec clab-lab02-r1 vtysh -c "show ip route ospf"
```

**What I saw:**

```
O>* 2.2.2.2/32 [110/10] via 10.0.12.2, eth2, weight 1, 00:03:11
O>* 3.3.3.3/32 [110/10] via 10.0.13.2, eth3, weight 1, 00:00:40
O>* 10.0.23.0/30 [110/20] via 10.0.12.2, eth2, weight 1, 00:00:40
  *                       via 10.0.13.2, eth3, weight 1, 00:00:40
O>* 192.168.3.0/24 [110/20] via 10.0.13.2, eth3, weight 1, 00:00:40
```

- **`[110/x]`**: 110 is OSPF's administrative distance, as on Cisco, and `x` is the total cost.
- **Every link cost 10, and loopbacks 0.** OSPF's cost is the reference bandwidth (100 Mb/s) divided by the link's bandwidth. These virtual links do not report a speed, so FRR uses its default of 10 Mb/s, giving 100 ÷ 10 = 10. I confirmed this in FRR's source code.
- **`192.168.3.0/24` costs 20 through the direct link.** Through r2 it would cost 30.
- **`10.0.23.0/30` has two next hops.** It is the same cost, 20, through r2 or through r3, so OSPF installed both. That is **equal-cost multipath (ECMP)**.

### Test 3: End to end

```bash
docker exec clab-lab02-pc1 ping -c 3 192.168.3.10
```

**What I saw:**

```
64 bytes from 192.168.3.10: icmp_seq=1 ttl=62 time=1.27 ms
64 bytes from 192.168.3.10: icmp_seq=2 ttl=62 time=0.226 ms
64 bytes from 192.168.3.10: icmp_seq=3 ttl=62 time=0.099 ms
```

```bash
docker exec clab-lab02-pc1 traceroute -n 192.168.3.10
```

**What I saw:**

```
 1  192.168.1.1  0.089 ms  0.012 ms  0.010 ms
 2  10.0.13.2  0.031 ms  0.030 ms  0.018 ms
 3  192.168.3.10  0.032 ms  0.027 ms  0.008 ms
```

`ttl=62` means two routers (64 − 2), against three in Lab 01. Traffic took the direct link and bypassed r2.

### Test 4: The direct link failed, and OSPF rerouted without losing a ping

I started a 20-second ping in the background, saving its output inside pc1, then shut down r1's link to r3 while it ran:

```bash
docker exec -d clab-lab02-pc1 sh -c "ping -c 40 -i 0.5 192.168.3.10 > /tmp/failover.txt"
```

```bash
docker exec clab-lab02-r1 vtysh -c "configure terminal" -c "interface eth3" -c "shutdown"
```

```bash
docker exec clab-lab02-r1 vtysh -c "show ip route 192.168.3.0/24"
```

**What I saw:**

```
Routing entry for 192.168.3.0/24
  Known via "ospf", distance 110, metric 30, best
  * 10.0.12.2, via eth2, weight 1
```

```bash
docker exec clab-lab02-pc1 cat /tmp/failover.txt
```

**What I saw** (shortened):

```
64 bytes from 192.168.3.10: icmp_seq=10 ttl=62 time=0.075 ms
64 bytes from 192.168.3.10: icmp_seq=11 ttl=62 time=0.059 ms
64 bytes from 192.168.3.10: icmp_seq=12 ttl=61 time=0.252 ms
64 bytes from 192.168.3.10: icmp_seq=13 ttl=61 time=0.065 ms
...
64 bytes from 192.168.3.10: icmp_seq=33 ttl=61 time=0.064 ms
```

- **No sequence numbers were missing**, so not one ping was lost.
- **The TTL changed from 62 to 61 between pings 11 and 12**, showing the exact half-second when traffic moved to the longer path through r2.

The traceroute confirmed the new path, `192.168.1.1`, `10.0.12.2`, `10.0.23.2`, then pc2.

The switch was instant because shutting down eth3 took the interface down on both directly connected routers, and OSPF reacted to that at once. If a device in the middle had failed instead, the interfaces would have stayed up, and OSPF would only have noticed when 40 seconds passed with no hellos (the dead interval). Production networks add **BFD** to detect that kind of failure in under a second.

I brought the link back with `no shutdown`. After about 45 seconds the r1–r3 adjacency was `Full` again and traffic returned to the direct link. This time r3 became DR on that link: both ends came up together, so there was a real election, and the highest router ID won.

### Test 5: Changing a cost to create equal paths

Setting the direct link's cost to 20 on r1 made both paths to pc2's LAN cost 30:

```bash
docker exec clab-lab02-r1 vtysh -c "configure terminal" -c "interface eth3" -c "ip ospf cost 20"
```

```bash
docker exec clab-lab02-r1 vtysh -c "show ip route 192.168.3.0/24"
```

**What I saw:**

```
Routing entry for 192.168.3.0/24
  Known via "ospf", distance 110, metric 30, best
  * 10.0.12.2, via eth2, weight 1
  * 10.0.13.2, via eth3, weight 1
```

r1 installed both paths. The cost only applied **outbound from r1**: r3's side of the link still cost 10, so replies from pc2 kept using the direct path. Traffic was shared one way and not the other, which is **asymmetric routing**.

I removed the cost with `no ip ospf cost`, and the route returned to one path at metric 20.

### Step 3: Saved the configurations into the repository

```bash
docker exec clab-lab02-r1 vtysh -c "write memory"
```

```bash
docker exec clab-lab02-r2 vtysh -c "write memory"
```

```bash
docker exec clab-lab02-r3 vtysh -c "write memory"
```

```bash
diff r1/frr.conf clab-lab02/r1/config/frr.conf
```

**What I saw** (shortened):

```
>  ip ospf passive
> router ospf
>  ospf router-id 1.1.1.1
>  network 1.1.1.1/32 area 0
>  network 10.0.12.0/30 area 0
>  network 10.0.13.0/30 area 0
>  network 192.168.1.0/24 area 0
```

No `ip ospf cost` line was saved, because I had removed it. I copied each saved file over its original:

```bash
cp clab-lab02/r1/config/frr.conf r1/frr.conf
```

```bash
cp clab-lab02/r2/config/frr.conf r2/frr.conf
```

```bash
cp clab-lab02/r3/config/frr.conf r3/frr.conf
```

### Test 6: Rebuilt from the repository

```bash
clab destroy -t lab02.clab.yml --cleanup
```

```bash
clab deploy -t lab02.clab.yml
```

```bash
docker exec clab-lab02-pc1 ping -c 3 192.168.3.10
```

**What I saw:**

```
64 bytes from 192.168.3.10: icmp_seq=1 ttl=61 time=5.95 ms
64 bytes from 192.168.3.10: icmp_seq=2 ttl=61 time=0.070 ms
64 bytes from 192.168.3.10: icmp_seq=3 ttl=62 time=0.058 ms
```

```bash
docker exec clab-lab02-r1 vtysh -c "show ip ospf neighbor"
```

**What I saw:**

```
Neighbor ID     Pri State           Up Time         Dead Time Address         Interface
2.2.2.2           1 Full/DR         12.458s           32.539s 10.0.12.2       eth2:10.0.12.1
3.3.3.3           1 Full/DR         7.458s            32.600s 10.0.13.2       eth3:10.0.13.1
```

The network came back with no manual configuration. Two things show it was still converging when I pinged:

- **The r1–r3 adjacency came up about 5 seconds after r1–r2.** Until then, the only path was through r2, so the first two replies arrived with `ttl=61` (three routers). The third, with `ttl=62`, came over the direct link.
- **With every router starting together, each link held a real election**, and the higher router ID won both of r1's links: r2 on r1–r2, and r3 on r1–r3.

| Test | Expected | Result |
|---|---|---|
| 1. Neighbours and DR | Adjacencies reach `Full`. DR not pre-empted by a later, higher router ID | ✅ |
| 2. Routes | `O` routes with correct costs, ECMP to `10.0.23.0/30` | ✅ |
| 3. End to end | Direct path, `ttl=62` | ✅ |
| 4. Link failure | Reroute through r2 with no lost pings, and back after recovery | ✅ |
| 5. Cost change | Equal costs give two next hops | ✅ |
| 6. Rebuild | Works with no manual configuration | ✅ |

---

## Issues I hit and how I fixed them

### 1. A command ran in PowerShell instead of Debian

**Symptom.** `cd ~/network-automation-labs/lab-02-ospf` failed with `Cannot find path 'C:\Users\<user>\network-automation-labs\lab-02-ospf'`.

**Root cause.** The window was Windows PowerShell (prompt `PS C:\...`), where `~` means the Windows home folder. The labs live inside Debian.

**Fix.** `wsl -d Debian` switched the window into Debian. I now check the prompt starts with my Debian user before running lab commands.

### 2. `% Unknown command: router ospf`

**Symptom.** The router rejected `router ospf`.

**Root cause.** I typed it at the `r1#` prompt, before `configure terminal`. As on Cisco, configuration commands only work in configuration mode.

**Fix.** `configure terminal` first. The prompt changes to `r1(config)#`.

### 3. Traffic had not returned to the direct link after `no shutdown`

**Symptom.** A traceroute run straight after bringing eth3 back still went through r2.

**Root cause.** The r1–r3 adjacency had to form again, including the DR wait, before OSPF would use the link.

**Fix.** Waiting about 45 seconds. Then the adjacency was `Full` and the traceroute showed the direct path.

### Notes

- **"Configuration applied with notes: No changes found to be committed!"** appeared whenever I entered an interface's configuration mode. It is not an error: FRR's management daemon reports that entering the mode changed nothing by itself.
- **Containerlab reported that version 0.82.0 was available.** I stayed on 0.81.1 so every lab in the series runs on the same version.

---

## Clean-up

```bash
clab destroy -t lab02.clab.yml --cleanup
```

---

## Command reference

| Command | What it does |
|---|---|
| `router ospf` | Enters OSPF configuration (in configuration mode) |
| `ospf router-id <id>` | Sets the router ID |
| `network <prefix> area <area>` | Runs OSPF on matching interfaces and advertises their networks |
| `ip ospf passive` | Advertises an interface's network without sending hellos on it (in interface mode) |
| `ip ospf cost <n>` / `no ip ospf cost` | Sets or removes an interface's outbound OSPF cost |
| `show ip ospf neighbor` | Lists neighbours, their state, and DR/BDR roles |
| `show ip route ospf` | Shows only the routes learnt by OSPF |
| `show ip route <prefix>` | Shows one route in detail, including every next hop |
| `vtysh -c "<cmd>" -c "<cmd>"` | Runs several router commands in one go, without opening the command line |

## What I learned

- OSPF needs neighbours: a router alone sends hellos but forms no adjacencies and learns nothing.
- The DR election is not pre-emptive. A later router with a higher router ID does not take over, so the DR is often whichever router came up first.
- An OSPF route's cost is the sum of outbound interface costs along the path, and equal costs give equal-cost multipath.
- Costs apply in one direction, so traffic can take different paths each way.
- OSPF rerouted around a failed link with no lost pings, because the interface went down on both routers. A failure that does not bring an interface down takes the dead interval to detect, which is why BFD exists.
- The TTL of replies showed the path changing, both during the failure and while the rebuilt network was converging.
- Loopback addresses make stable router IDs, because a loopback never goes down.

---

## References

Official documentation I used while building and testing this lab.

| What I did | Documentation |
|---|---|
| Configured OSPF in FRR | [FRR 10.7.1: OSPFv2 user documentation](https://github.com/FRRouting/frr/blob/frr-10.7.1/doc/user/ospfd.rst) |
| Understood DR election, costs and adjacencies | [RFC 2328: OSPF Version 2](https://www.rfc-editor.org/rfc/rfc2328) |
| Ran the routers with the `frr` kind | [Containerlab: FRRouting kind](https://containerlab.dev/manual/kinds/frr/) |
| Ran the PCs | [Containerlab: Linux kind](https://containerlab.dev/manual/kinds/linux/) |
| Destroyed the lab and its folder | [Containerlab: destroy command](https://containerlab.dev/cmd/destroy) |