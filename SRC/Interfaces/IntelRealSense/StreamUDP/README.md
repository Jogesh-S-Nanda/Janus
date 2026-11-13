# Intel RealSense UDP Video Streaming

> **Author**  : Jogesh S Nanda  
> **Licence** : RIL and InSpireLab IISC  
> **Version** : 1.0 — 02/04/2026

---

## Overview

Two-PC pipeline for streaming live color video from an Intel RealSense camera over UDP.

```
PC1  ──  RealSense camera  ──►  UDPServer.py  ──[UDP]──►  UDPClient.py  ──  display / processing
```

| File            | Role                                                                          |
|-----------------|-------------------------------------------------------------------------------|
| `UDPServer.py`  | Reads from camera, JPEG-encodes frames, fragments and sends over UDP          |
| `UDPClient.py`  | Receives fragments, reassembles frames, decodes and displays / processes them |

### UDP vs TCP — when to use which

| Feature               | TCP (`StreamTCP`)          | UDP (`StreamUDP`)                      |
|-----------------------|----------------------------|----------------------------------------|
| Delivery guarantee    | Yes (stream, in-order)     | No (best-effort, may drop/reorder)     |
| Latency               | Higher (ACK overhead)      | Lower (fire-and-forget)                |
| Packet loss handling  | Automatic retransmit       | Incomplete frames silently dropped     |
| Connection model      | `accept()` / `connect()`   | HELLO registration datagram            |
| Best for              | Reliable recording/logging | Low-latency teleoperation / live HRI   |

---

## Installation

```bash
pip install pyrealsense2 opencv-python numpy
```

> GStreamer is **not** required — this implementation uses pure Python sockets.

---

## Quick Start

**PC1 — run the server** (camera attached here):

```bash
python UDPServer.py --host 0.0.0.0 --port 9999 --width 640 --height 480 --fps 30
```

**PC2 — run the client** (display here):

```bash
python UDPClient.py --host <PC1-IP> --port 9999 --listen-port 9998
```

Press **ESC** or **Q** inside the display window to quit.

### Registration handshake

Unlike TCP there is no `accept()`. The client sends a single `HELLO` datagram to the server.
The server records the client's `(ip, port)` from that packet and begins streaming to it.
This means the server never needs to know the client IP in advance.

```
Client                          Server
  │──── HELLO ──────────────────►│  (server learns client address)
  │◄─── JPEG fragments ──────────│  (stream starts)
```

---

## API Reference

### `RealSenseCamera`

Thin wrapper around the `pyrealsense2` pipeline. Identical to the TCP version —
manages camera lifecycle and exposes a single `read()` method.

#### Constructor

```python
cam = RealSenseCamera(width=640, height=480, fps=30)
```

| Parameter | Type  | Default | Description                   |
|-----------|-------|---------|-------------------------------|
| `width`   | `int` | `640`   | Color stream width in pixels  |
| `height`  | `int` | `480`   | Color stream height in pixels |
| `fps`     | `int` | `30`    | Desired camera frame rate     |

#### Methods

| Method    | Returns              | Description                          |
|-----------|----------------------|--------------------------------------|
| `start()` | `None`               | Start the RealSense pipeline         |
| `stop()`  | `None`               | Stop the pipeline and release camera |
| `read()`  | `np.ndarray \| None` | Return the next BGR color frame      |

---

### `UDPVideoServer`

Binds a UDP socket, starts the camera, waits for a client `HELLO`, then streams
JPEG-encoded frames as fixed-size fragments. When the client disconnects or goes
silent the server waits for the next `HELLO`.

#### Constructor

```python
server = UDPVideoServer(host="0.0.0.0", port=9999, width=640, height=480, fps=30)
```

| Parameter | Type    | Default     | Description                                   |
|-----------|---------|-------------|-----------------------------------------------|
| `host`    | `str`   | `"0.0.0.0"` | Bind address (`"0.0.0.0"` = all interfaces)   |
| `port`    | `int`   | `9999`      | UDP port to listen on                         |
| `width`   | `int`   | `640`       | Camera stream width in pixels                 |
| `height`  | `int`   | `480`       | Camera stream height in pixels                |
| `fps`     | `int`   | `30`        | Desired camera frame rate                     |

#### Methods

| Method   | Returns | Description                                         |
|----------|---------|-----------------------------------------------------|
| `run()`  | `None`  | Start camera and block in the serve loop            |
| `stop()` | `None`  | Signal the serve loop to exit cleanly (thread-safe) |

#### Example — basic server

```python
from UDPServer import UDPVideoServer

server = UDPVideoServer(host="0.0.0.0", port=9999)
server.run()    # blocks; press Ctrl-C to stop
```

#### Example — server in a background thread

```python
import threading
from UDPServer import UDPVideoServer

server = UDPVideoServer(port=9999, width=1280, height=720, fps=15)
t = threading.Thread(target=server.run, daemon=True)
t.start()

input("Press Enter to stop...\n")
server.stop()
t.join()
```

---

### `UDPVideoClient`

Sends a `HELLO` datagram to register with the server, then receives fragmented UDP
datagrams, reassembles complete frames, and displays them. Out-of-order and
duplicate datagrams are handled; incomplete frames are silently dropped.

#### Constructor

```python
client = UDPVideoClient(
    host        = "192.168.1.10",
    port        = 9999,
    listen_port = 9998,
)
```

| Parameter     | Type  | Default       | Description                                      |
|---------------|-------|---------------|--------------------------------------------------|
| `host`        | `str` | `"127.0.0.1"` | Server IP address or hostname (required)         |
| `port`        | `int` | `9999`        | Server UDP port                                  |
| `listen_port` | `int` | `9998`        | Local port this client binds to for receiving    |

#### Methods

| Method   | Returns | Description                                              |
|----------|---------|----------------------------------------------------------|
| `run()`  | `None`  | Register with server and block in receive/display loop   |
| `stop()` | `None`  | Signal the receive loop to exit cleanly (thread-safe)    |

#### Example — basic client (display only)

```python
from UDPClient import UDPVideoClient

client = UDPVideoClient(host="192.168.1.10", port=9999, listen_port=9998)
client.run()    # blocks; press ESC or Q to quit
```

#### Example — custom listen port (multiple clients on same machine)

```python
# first client
client_a = UDPVideoClient(host="192.168.1.10", port=9999, listen_port=9998)

# second client on a different local port
client_b = UDPVideoClient(host="192.168.1.10", port=9999, listen_port=9997)
```

---

## Use Case — Object Detection on Received Frames

Subclass `UDPVideoClient` and override `_receive_loop` to process each reassembled
frame before (or instead of) displaying it. The example below uses **YOLOv8**.

```python
"""
udp_detection_client.py
-----------------------
Subclass UDPVideoClient to run YOLOv8 on every received frame.

Requirements:
    pip install ultralytics
"""

import struct
import cv2
from ultralytics import YOLO
from UDPClient import UDPVideoClient, HEADER_FMT, HEADER_SIZE, RECV_BUF_BYTES, FRAME_BUFFER_DEPTH
from collections import defaultdict


class UDPDetectionClient(UDPVideoClient):
    """
    UDPVideoClient extended with YOLOv8 object detection.
    Annotates each received frame with bounding boxes before display.
    """

    def __init__(self, model_path: str = "yolov8n.pt", **kwargs):
        """
            constructor — load YOLO model and forward args to the base class.
        :parameter model_path: path to YOLOv8 weights file
        """
        super().__init__(**kwargs)
        self._model = YOLO(model_path)

    def _receive_loop(self) -> None:
        """
            override receive loop to inject detection after frame reassembly.
        :return:
        """
        while self._running:
            if self._sock is None:
                break
            try:
                data, _ = self._sock.recvfrom(RECV_BUF_BYTES)
            except Exception:
                continue

            if len(data) < HEADER_SIZE:
                continue

            frame_id, chunk_idx, total_chunks = struct.unpack(
                HEADER_FMT, data[:HEADER_SIZE]
            )
            self._frame_buf[frame_id][chunk_idx] = data[HEADER_SIZE:]

            if frame_id > self._latest_frame_id:
                self._latest_frame_id = frame_id

            # evict stale frames
            for fid in [f for f in self._frame_buf
                        if f < self._latest_frame_id - FRAME_BUFFER_DEPTH]:
                del self._frame_buf[fid]

            # decode when all chunks have arrived
            if len(self._frame_buf[frame_id]) == total_chunks:
                frame = self._try_assemble(frame_id, total_chunks)
                del self._frame_buf[frame_id]

                if frame is not None:
                    # run YOLOv8 inference
                    results    = self._model(frame, verbose=False)
                    annotated  = results[0].plot()

                    cv2.imshow("UDP Detection Stream", annotated)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        self.stop()


if __name__ == "__main__":
    client = UDPDetectionClient(
        model_path  = "yolov8n.pt",
        host        = "192.168.1.10",
        port        = 9999,
        listen_port = 9998,
    )
    client.run()
```

### Detection pipeline diagram

```
UDPServer (PC1)                         UDPDetectionClient (PC2)
───────────────                         ─────────────────────────────────────────
RealSense camera                        _receive_loop()
  │                                       │
  ▼                                       ├─► reassemble chunks  → JPEG bytes
JPEG encode                               │
  │                                       ├─► _decode_frame()    → BGR np.ndarray
  ▼                                       │
fragment into ≤60 KB chunks              ├─► YOLO(frame)         → Results
  │                                       │
  └──── UDP datagrams ─────────────────►  ├─► results[0].plot()  → annotated frame
                                          │
                                          └─► cv2.imshow()
```

---

## Wire Protocol

### Per-datagram layout

```
┌─────────────────┬──────────────┬──────────────────┬─────────────────────────┐
│  frame_id (4 B) │ chunk_idx(2B)│ total_chunks (2B)│  chunk payload (≤60 KB) │
│   uint32 BE     │  uint16 BE   │    uint16 BE     │  raw JPEG bytes         │
└─────────────────┴──────────────┴──────────────────┴─────────────────────────┘
 ◄──────────────── HEADER_SIZE = 8 bytes ──────────────►
```

- Header format string: `"!IHH"` (big-endian, `struct` module)
- `frame_id` wraps at 2³² — rolling counter incremented per frame
- `chunk_idx` is zero-based; `total_chunks` is the total number of fragments for this frame
- Maximum payload per datagram: **60 000 bytes** (safely below the 65 507 byte UDP limit)

### Reassembly logic

```
Receiver buffer:  { frame_id → { chunk_idx → bytes } }

On each datagram arrival:
    1. Parse header  →  (frame_id, chunk_idx, total_chunks)
    2. Store chunk   →  buffer[frame_id][chunk_idx] = payload
    3. If len(buffer[frame_id]) == total_chunks  →  reassemble + decode + display
    4. Evict frames with frame_id < latest - FRAME_BUFFER_DEPTH  (default 5)
```

Incomplete frames (caused by UDP packet loss) are silently discarded — the next
complete frame is displayed without any visual artefacts.

---

## Command-Line Arguments

### UDPServer.py

| Argument   | Default     | Description                       |
|------------|-------------|-----------------------------------|
| `--host`   | `0.0.0.0`   | Bind address                      |
| `--port`   | `9999`      | UDP port                          |
| `--width`  | `640`       | Camera stream width (pixels)      |
| `--height` | `480`       | Camera stream height (pixels)     |
| `--fps`    | `30`        | Camera frame rate                 |

### UDPClient.py

| Argument        | Default       | Description                                   |
|-----------------|---------------|-----------------------------------------------|
| `--host`        | `127.0.0.1`   | Server IP / hostname                          |
| `--port`        | `9999`        | Server UDP port                               |
| `--listen-port` | `9998`        | Local port for receiving datagrams            |

---

## Firewall note

UDP requires the **receive port** on the client machine to be open inbound:

```bash
# Linux — open the client listen port
sudo ufw allow 9998/udp

# Linux — open the server port
sudo ufw allow 9999/udp
```