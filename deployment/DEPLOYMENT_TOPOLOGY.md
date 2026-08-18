# RECLAIM Live Deployment Topology

**Status:** authoritative platform record
**Effective:** 2026-08-17

## Live systems

| Component | Platform | Responsibility |
|---|---|---|
| RECLAIM hardware | cRIO + LabVIEW | Authoritative telemetry and process sequencing |
| Edge gateway | Windows 10 laptop | Receives cRIO TCP telemetry, frames and buffers it, and posts authenticated live telemetry |
| Predictive-engine VM | Cloud-hosted Windows Server 2025 guest in Kubernetes-managed infrastructure | Runs the dual predictive engine, Cloudflare tunnel client, state bridge, and existing VM Convene agent |
| Convene | External service | Receives the VM `sim_` predictive namespace and separate laptop `gw_` audit namespace |

The Kubernetes layer hosts/orchestrates the Windows VM. Guest deployment and
troubleshooting use Windows services, PowerShell, NTFS paths, and Windows ACLs.
Linux guest commands such as `systemctl`, `journalctl`, `hostnamectl`, `ss`, and
paths under `/opt`, `/etc`, or `/var/lib` do not apply.

There is no Raspberry Pi and no Linux host in the live telemetry path. The
repository directory name `pi_gateway` is retained temporarily to avoid a risky
pre-demonstration package rename; it denotes software running on the Windows 10
laptop.

## Live data paths

```text
cRIO / LabVIEW
  -> direct Ethernet TCP 9070
Windows 10 laptop gateway
  -> authenticated HTTPS POST /ingest
Cloudflare route
  -> 127.0.0.1:8078
Windows Server 2025 predictive engine
  -> authenticated loopback GET /state
Windows state bridge
  -> atomic C:\ConveneAgent\sim_vars.json
Existing VM Convene agent
  -> Convene sim_ namespace

Windows 10 gateway GET 127.0.0.1:9080/latest
  -> existing laptop Convene agent
  -> separate Convene gw_ audit namespace
```

The predictive `/command` representation remains advisory. Neither Convene,
the state bridge, nor the gateway may treat it as actuator authority in this
integration phase.

## Platform ownership boundary

- Kubernetes/hosting operators own the outer VM workload, persistence, network,
  and recovery policy.
- Windows VM operators own the guest services, release directory, ACLs, secrets,
  port 8078, Cloudflare client, bridge, and VM Convene agent.
- Gateway operators own the Windows 10 laptop, direct cRIO network, firewall rule,
  durable queue, gateway task, and `gw_` audit publication.
- Controls operators retain hardware interlock and process authority.

Do not use Kubernetes container lifecycle as a substitute for the engine's
persistent run/sequence state. The Windows guest state file must survive an engine
service restart; the infrastructure owner must separately confirm whether it also
survives VM/workload rescheduling.

## Historical artifacts

Git history contains earlier Linux-cloud-VM and Raspberry-Pi deployment plans.
They are not deployment alternatives. Current operational documents must link to
this topology and use Windows procedures exclusively.
