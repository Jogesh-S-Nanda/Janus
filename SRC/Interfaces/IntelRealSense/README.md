# Intel RealSense Interface Module

> **Author**  : Jogesh S Nanda  
> **Licence** : RIL and InSpireLab IISC  
> **Version** : 1.0 — 02/04/2026

---

## Overview

This module provides everything needed to capture and stream live color video from an
**Intel RealSense D-series** depth camera within the CRF framework.  Two independent
transport implementations are included so the right one can be chosen for each use case.

```
SRC/Interfaces/IntelRealSense/
│
├── StreamTCP/              ← reliable streaming  (TCP)
│   ├── TCPServer.py        ← runs on PC1 (camera attached)
│   ├── TCPClient.py        ← runs on PC2 (display / processing)
│   └── README.md           ← TCP-specific API reference
│
├── StreamUDP/              ← low-latency streaming  (UDP)
│   ├── UDPServer.py        ← runs on PC1 (camera attached)
│   ├── UDPClient.py        ← runs on PC2 (display / processing)
│   └── README.md           ← UDP-specific API reference
│
├── usb_access.sh           ← one-time Linux USB permission setup
└── README.md               ← this file
```

---

## Hardware Requirements

| Item | Specification |
|------|---------------|
| Camera | Intel RealSense D415, D435, D435i, D455, or D457 |
| Host connection | USB 3.0 (SuperSpeed) — **USB 2.0 gives reduced frame rate** |
| OS | Ubuntu 20.04 / 22.04 / 24.04 (tested), Windows 10/11 (pyrealsense2 supported) |
| Python | 3.8 or later |

> **Reference hardware pages**
> - D435i product page: https://www.intelrealsense.com/depth-camera-d435i/
> - D455 product page : https://www.intelrealsense.com/depth-camera-d455/
> - Full product lineup: https://www.intelrealsense.com/stereo-depth/

---

## Installation

### 1. librealsense SDK

```bash
# Ubuntu — add Intel RealSense repository
sudo apt-key adv --keyserver keys.gnupg.net --recv-key F6E65AC044F831AC80A06380C8B3A55A6F3EFCDE
sudo add-apt-repository "deb https://librealsense.intel.com/Debian/apt-repo $(lsb_release -cs) main"
sudo apt update
sudo apt install librealsense2-dkms librealsense2-utils librealsense2-dev
```

### 2. Python packages

```bash
pip install pyrealsense2 opencv-python numpy
```

### 3. USB device permissions (Linux — one time only)

Run the provided setup script once after first connecting the camera:

```bash
bash SRC/Interfaces/IntelRealSense/usb_access.sh
```

See [USB Access Setup](#usb-access-setup--usb_accesssh) below for full details.

---

## Which Transport Should I Use?

| Requirement | Use |
|---|---|
| Reliable delivery — every frame must arrive (logging, recording) | **StreamTCP** |
| Lowest possible latency — teleoperation, live HRI | **StreamUDP** |
| Simple reconnection — client can crash and restart | **StreamTCP** |
| Multiple clients receiving the same stream | **StreamUDP** (run one client per port) |
| Local network with no firewall restrictions | Either |
| Strict firewall — only TCP ports open | **StreamTCP** |

### Quick comparison

| Feature | StreamTCP | StreamUDP |
|---|---|---|
| Transport | TCP socket | UDP datagram |
| Delivery guarantee | Yes — in-order, no loss | No — best-effort |
| Latency | Higher (ACK overhead) | Lower (fire-and-forget) |
| Packet loss | Automatic retransmit | Incomplete frames silently dropped |
| Connection model | `accept()` / `connect()` | HELLO registration datagram |
| Reconnection | Automatic with exponential back-off | Re-send HELLO to re-register |
| Wire format | `uint64` length prefix + `pickle` payload | 8-byte header + raw JPEG chunks |
| Default port | 9999 | 9999 (server) / 9998 (client listen) |

---

## StreamTCP — Quick Start

> Full API reference: [`StreamTCP/README.md`](StreamTCP/README.md)

**PC1 — server** (camera attached):

```bash
python SRC/Interfaces/IntelRealSense/StreamTCP/TCPServer.py \
    --host 0.0.0.0 --port 9999 --width 640 --height 480 --fps 30
```

**PC2 — client** (display):

```bash
python SRC/Interfaces/IntelRealSense/StreamTCP/TCPClient.py \
    --host <PC1-IP> --port 9999
```

### Use in code

```python
# --- server side (PC1) ---
from StreamTCP.TCPServer import TCPVideoServer

server = TCPVideoServer(host="0.0.0.0", port=9999)
server.run()   # blocks; Ctrl-C to stop

# --- client side (PC2) ---
from StreamTCP.TCPClient import TCPVideoClient

client = TCPVideoClient(host="192.168.1.10", port=9999)
client.run()   # blocks; ESC or Q to quit
```

---

## StreamUDP — Quick Start

> Full API reference: [`StreamUDP/README.md`](StreamUDP/README.md)

**PC1 — server** (camera attached):

```bash
python SRC/Interfaces/IntelRealSense/StreamUDP/UDPServer.py \
    --host 0.0.0.0 --port 9999 --width 640 --height 480 --fps 30
```

**PC2 — client** (display):

```bash
python SRC/Interfaces/IntelRealSense/StreamUDP/UDPClient.py \
    --host <PC1-IP> --port 9999 --listen-port 9998
```

### Use in code

```python
# --- server side (PC1) ---
from StreamUDP.UDPServer import UDPVideoServer

server = UDPVideoServer(host="0.0.0.0", port=9999)
server.run()   # blocks; Ctrl-C to stop

# --- client side (PC2) ---
from StreamUDP.UDPClient import UDPVideoClient

client = UDPVideoClient(host="192.168.1.10", port=9999, listen_port=9998)
client.run()   # blocks; ESC or Q to quit
```

---

## Integrating into the Shared Control Launcher

The `Remote/IntelCamera.py` and `Master/IntelCamera.py` wrapper scripts are already
provided under `Shared Control/Version 1/`.  They are launched automatically by
`launch-remote.py` and `launch-master.py` via the `Launcher` class — no manual
invocation is needed in a normal experiment.

```
PC1 (Remote)                          PC2 (Master)
─────────────────────────────         ──────────────────────────────────────
launch-remote.py                      launch-master.py
  └─ Remote/IntelCamera.py              └─ Master/IntelCamera.py
       └─ TCPVideoServer (port 9999)          └─ TCPVideoClient → cv2.imshow
```

To swap from TCP to UDP, edit the imports in `Remote/IntelCamera.py` and
`Master/IntelCamera.py` to use `UDPVideoServer` / `UDPVideoClient` respectively.

---

## USB Access Setup — `usb_access.sh`

The RealSense camera appears on Linux as a USB device.  Without the correct
permissions a non-root user cannot open the device, and `pyrealsense2` raises a
permission error.

### What the script does

| Step | Action |
|------|--------|
| 1 | Searches for the FT232 USB device via `lsusb` and reports the node (`/dev/ttyUSBx`) |
| 2 | Writes a udev rule to `/etc/udev/rules.d/99-usb-permissions.rules` granting `MODE=0666` and `GROUP=dialout` |
| 3 | Reloads udev (`udevadm control --reload-rules && udevadm trigger`) so the rule applies immediately |
| 4 | Adds the current user to the `dialout` group (`usermod -a -G dialout $USER`) |
| 5 | Writes a sudoers drop-in (`/etc/sudoers.d/python-usb`) so Python scripts can be run with `sudo` without a password |

### Usage

```bash
# run once after first connecting the camera
bash SRC/Interfaces/IntelRealSense/usb_access.sh
```

> **Note** — a re-login (or `newgrp dialout`) is required for the `dialout` group
> membership to become active in the current shell session.

### Verify the camera is accessible

```bash
# check that the RealSense device is enumerated
rs-enumerate-devices

# or from Python
python3 -c "import pyrealsense2 as rs; ctx = rs.context(); print(len(ctx.devices), 'device(s) found')"
```

### Manual udev rule (if you prefer not to run the script)

```bash
# create the rule file
sudo tee /etc/udev/rules.d/99-realsense.rules > /dev/null <<'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="8086", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb_device", ATTRS{idVendor}=="8086", MODE="0666", GROUP="plugdev", TAG+="uaccess"
EOF

# reload
sudo udevadm control --reload-rules && sudo udevadm trigger

# add user to plugdev group
sudo usermod -a -G plugdev $USER
```

---

## Firewall

Open the required ports on both machines before running across a network:

```bash
# TCP streaming — open on the server machine
sudo ufw allow 9999/tcp

# UDP streaming — open on the server and client machines
sudo ufw allow 9999/udp   # server receive (HELLO)
sudo ufw allow 9998/udp   # client receive (stream)
```

---

## Reference Documentation

### Intel RealSense SDK

| Resource | Link |
|---|---|
| librealsense GitHub | https://github.com/IntelRealSense/librealsense |
| Python pyrealsense2 API | https://intelrealsense.github.io/librealsense/python_docs/ |
| SDK release notes | https://github.com/IntelRealSense/librealsense/releases |
| Python examples | https://github.com/IntelRealSense/librealsense/tree/master/wrappers/python/examples |

### Hardware Manuals

| Document | Link |
|---|---|
| D400 series datasheet | https://www.intelrealsense.com/wp-content/uploads/2022/11/Intel-RealSense-D400-Series-Datasheet.pdf |
| D400 series product family | https://www.intelrealsense.com/stereo-depth/ |
| Best practices — depth quality | https://dev.intelrealsense.com/docs/d400-series-visual-presets |
| Getting started guide | https://www.intelrealsense.com/get-started-depth-camera/ |

### Tutorials and Community

| Resource | Link |
|---|---|
| Intel RealSense developer site | https://dev.intelrealsense.com/ |
| Community forum | https://community.intel.com/t5/Intel-RealSense-Technology/bd-p/realsense |
| OpenCV with RealSense tutorial | https://github.com/IntelRealSense/librealsense/blob/master/doc/installation.md |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: Failed to start RealSense pipeline` | No camera found or permission denied | Run `usb_access.sh`, re-login, check USB 3.0 port |
| `cv2.imdecode returned None` | JPEG decode failure (corrupted frame) | Logged as warning; next frame will recover automatically |
| No frames displayed on client | Firewall blocking UDP/TCP port | Open ports with `ufw allow` (see Firewall section) |
| High latency on TCP | Network congestion or slow CPU encoding | Lower resolution/FPS, or switch to StreamUDP |
| Dropped frames on UDP | Buffer overflow on receiver | Increase `SO_RCVBUF` or lower server FPS |
| `pyrealsense2` import error | SDK not installed | Run `pip install pyrealsense2` and check `librealsense2` apt packages |
| Camera disconnects during run | USB bandwidth issue | Use a USB 3.0 port; avoid USB hubs |