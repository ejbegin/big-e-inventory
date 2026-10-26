# Continuous Deployment & Architecture Guide
## Big E Inventory -> FamilyBrain

**Big E Inventory** (Square Stock Management, Multi-Location Transfers & Demand Forecasting) runs 24/7 on your dedicated Ubuntu Mini-PC (`familybrain`) on your Tailscale mesh and local network, co-located alongside **Personal Brain**, **Kids 3D Print Manager**, and **Scout Coach**.

---

## 1. Multi-App Production Architecture

```
 [ Local Workstation (businesspc) ]
               │
               │ git push origin main / .\tools\deploy.ps1
               ▼
 [ GitHub Repository ] (github.com/ejbegin/big-e-inventory)
               │
               ├──────► [ familybrain Systemd Auto-Update Timer ] (Pulls origin/main every 3 min)
               │
               └──────► [ Instant Workstation Deploy ] (powershell .\tools\deploy.ps1)
                             │ (SSH over LAN 192.168.1.10 / Tailscale 100.64.115.12)
                             ▼
                 [ /opt/big-e-inventory on familybrain ]
                             │
                             ├──────► Service: big-e-inventory.service (Port 8085 Web / Gunicorn)
                             ├──────► Python Virtualenv: /opt/big-e-inventory/.venv (Astral uv / 3.12)
                             └──────► Persistent Data: /opt/big-e-inventory/data/ (Caches, Logos, Settings)
```

### Shared Ecosystem Topology

| Application | Port | Working Directory | Storage Location | Auto-Deploy Timer |
| :--- | :--- | :--- | :--- | :--- |
| **Kids 3D Print Manager** | `8001` | `/opt/kids-3d-print-manager` | SSD + `/mnt/storage/3D Models` | `kids-print-manager-autoupdate.timer` |
| **Personal Brain Web & MCP** | `8007` / `8008` | `/opt/personal-brain` | SSD + `/mnt/storage/personal-brain` | `personal-brain-autoupdate.timer` |
| **Scout Coach Web & MCP** | `8083` / `8084` | `/opt/scout-coach/ask-a-scout` | NVMe SSD (`/opt/scout-coach`) | `scout-coach-autoupdate.timer` |
| **Big E Inventory** | `8085` | `/opt/big-e-inventory` | NVMe SSD (`/opt/big-e-inventory/data`) | `big-e-inventory-autoupdate.timer` |

---

## 2. Accessing Big E Inventory

Accessible from any phone, tablet, or workstation connected to your Tailscale network or home Wi-Fi:

- **Web Dashboard (Local)**: `http://192.168.1.10:8085`
- **Web Dashboard (Tailscale)**: `http://100.64.115.12:8085` (or `http://familybrain.tail847443.ts.net:8085`)
- **Direct Hub Link**: `http://192.168.1.10/bige` or `http://192.168.1.10/inventory`

---

## 3. Deployment Workflow

### Option 1: Fast Workstation Deploy (Instant)
From PowerShell in the `Big E Inventory` root folder:
```powershell
.\tools\deploy.ps1
```
Or with a custom commit message:
```powershell
.\tools\deploy.ps1 -CommitMessage "feat: improve inventory transfers"
```

### Option 2: Push-to-Deploy (Background)
Simply push to GitHub:
```bash
git push origin main
```
`familybrain` runs `big-e-inventory-autoupdate.timer` every 3 minutes. When a new commit is detected on `origin/main`, the server automatically pulls the commit, updates Python dependencies if required, and restarts `big-e-inventory.service`.

---

## 4. Server Management Commands

From an SSH terminal on `familybrain`:
```bash
# Check service status
sudo systemctl status big-e-inventory.service

# View live service logs
sudo journalctl -u big-e-inventory.service -f

# Check auto-update timer
systemctl status big-e-inventory-autoupdate.timer
```
