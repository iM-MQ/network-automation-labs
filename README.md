# Network Automation Labs

Refreshing my CCNA routing skills hands-on, then automating and testing the network the way I now test code. Each lab builds a virtual network of real routers with [Containerlab](https://containerlab.dev), configures it, breaks it on purpose, and records what I saw.

The routers run [FRRouting (FRR)](https://frrouting.org), an open-source routing suite whose command line is very close to Cisco IOS (`configure terminal`, `ip route`, `show ip route`). Every topology and router configuration is a file in this repository, so any lab can be rebuilt from scratch with one command.

## Labs

| Lab | Topic | Status |
|---|---|---|
| [01](lab-01-static-routing) | Static routing: three routers, default routes on the stubs, specific routes on the transit router, and the return-path problems in between | Complete ✅ |
| [02](lab-02-ospf) | OSPF: neighbours, DR election, costs and equal-cost multipath, and rerouting around a failed link with no lost pings | Complete ✅ |
| 03 | BGP between two sites that run OSPF inside, with route filtering | Planned ⏳ |
| 04 | Python automation: collect routing tables and back up every router's configuration | Planned ⏳ |
| 05 | Network tests in CI: pytest checks routes and neighbours, and GitHub Actions builds and tests the whole network on every push | Planned ⏳ |

## Where this fits

| Repository | What it covers |
|---|---|
| [azure-landing-zone](https://github.com/iM-MQ/azure-landing-zone) | Azure networking at scale: hub-and-spoke, Azure Firewall and route tables |
| [fastapi-asset-register](https://github.com/iM-MQ/fastapi-asset-register) | The testing and CI approach that Labs 04 and 05 apply to a network |
| **network-automation-labs** | The routing fundamentals underneath both, built and tested as code |

## Prerequisites

| Requirement | Version used | Purpose |
|---|---|---|
| Windows 11 with WSL2 | WSL 2.7 | Runs Linux on Windows |
| Debian on WSL | From `wsl --install -d Debian` | A Linux environment kept just for these labs |
| Containerlab | 0.81.1 | Builds the virtual networks |
| Docker Engine, inside Debian | 28.5 | Runs the routers. Installed by Containerlab's setup script, separate from Docker Desktop |
| VS Code + WSL extension | Latest | Editing files inside Debian |

## First-time setup

These steps follow [Containerlab's Windows guide](https://containerlab.dev/windows/). In PowerShell:

```powershell
wsl --install -d Debian
```

Then inside Debian:

```bash
sudo apt update
```

```bash
sudo apt -y install curl
```

```bash
curl -sL https://containerlab.dev/setup | sudo -E bash -s "all"
```

Close Debian, run `wsl --terminate Debian` in PowerShell, reopen it with `wsl -d Debian`, then check:

```bash
clab version
```

Docker Desktop's WSL integration must stay **off** for this Debian environment, so the two Docker installations do not conflict.

## Practices followed

- Every topology and router configuration lives in this repository, and each lab is rebuilt from it to prove it is complete
- Image versions are pinned, so results are repeatable
- Containerlab's working folders are excluded by `.gitignore`
- Every README records the commands I ran, what I saw, and the issues I hit