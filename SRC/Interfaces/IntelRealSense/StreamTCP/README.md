# Intel RealSense TCP Video Streaming

> **Author**  : Jogesh S Nanda  
> **Licence** : RIL and InSpireLab IISC  
> **Version** : 1.0 — 02/04/2026

---

## Overview

Two-PC pipeline for streaming live color video from an Intel RealSense camera over TCP.

```
PC1  ──  RealSense camera  ──►  TCPServer.py  ──[TCP]──►  TCPClient.py  ──  display / processing
```

| File            | Role                                                        |
|-----------------|-------------------------------------------------------------|
| `TCPServer.py`  | Reads from the camera, JPEG-encodes frames, sends over TCP  |
| `TCPClient.py`  | Receives frames, decodes them, displays or processes them   |

---

## Installation

```bash
pip install pyrealsense2 opencv-python numpy
```

---

## Quick Start

**PC1 — run the server** (camera attached here):

```bash
python TCPServer.py --host 0.0.0.0 --port 9999 --width 640 --height 480 --fps 30
```

**PC2 — run the client** (display / processing here):

```bash
python TCPClient.py --host <PC1-IP> --port 9999
```

Press **ESC** or **Q** inside the display window to quit.

---

## API Reference

### `RealSenseCamera`

Thin wrapper around the `pyrealsense2` pipeline. Manages camera lifecycle and exposes a single `read()` method.

#### Constructor

```python
cam = RealSenseCamera(width=640, height=480, fps=30)
```

| Parameter | Type  | Default | Description                        |
|-----------|-------|---------|------------------------------------|
| `width`   | `int` | `640`   | Color stream width in pixels       |
| `height`  | `int` | `480`   | Color stream height in pixels      |
| `fps`     | `int` | `30`    | Desired camera frame rate          |

#### Methods

| Method      | Returns              | Description                                      |
|-------------|----------------------|--------------------------------------------------|
| `start()`   | `None`               | Start the RealSense pipeline                     |
| `stop()`    | `None`               | Stop the pipeline and release the camera         |
| `read()`    | `np.ndarray \| None` | Return the next BGR color frame                  |

#### Example — standalone camera capture

```python
from RealSenseCamera import RealSenseCamera
import cv2

cam = RealSenseCamera(width=1280, height=720, fps=30)
cam.start()

while True:
    frame = cam.read()
    if frame is None:
        continue

    cv2.imshow("Camera", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.stop()
cv2.destroyAllWindows()
```

#### Example — context manager (auto start/stop)

```python
with RealSenseCamera(width=640, height=480, fps=30) as cam:
    for _ in range(100):
        frame = cam.read()
        if frame is not None:
            cv2.imwrite(f"frame_{_:04d}.png", frame)
```

---

### `TCPVideoServer`

Binds a TCP socket, starts the camera, and streams JPEG-encoded frames to one client at a time.
After a client disconnects the server automatically waits for the next connection.

#### Constructor

```python
server = TCPVideoServer(host="0.0.0.0", port=9999, width=640, height=480, fps=30)
```

| Parameter | Type    | Default     | Description                                   |
|-----------|---------|-------------|-----------------------------------------------|
| `host`    | `str`   | `"0.0.0.0"` | Bind address (`"0.0.0.0"` = all interfaces)   |
| `port`    | `int`   | `9999`      | TCP port to listen on                         |
| `width`   | `int`   | `640`       | Camera stream width in pixels                 |
| `height`  | `int`   | `480`       | Camera stream height in pixels                |
| `fps`     | `int`   | `30`        | Desired camera frame rate                     |

#### Methods

| Method   | Returns | Description                                          |
|----------|---------|------------------------------------------------------|
| `run()`  | `None`  | Start the camera and block in the serve loop         |
| `stop()` | `None`  | Signal the serve loop to exit cleanly (thread-safe)  |

#### Example — basic server

```python
from TCPServer import TCPVideoServer

server = TCPVideoServer(host="0.0.0.0", port=9999)
server.run()    # blocks; press Ctrl-C to stop
```

#### Example — server in a background thread

```python
import threading
from TCPServer import TCPVideoServer

server = TCPVideoServer(port=9999, width=1280, height=720, fps=15)
t = threading.Thread(target=server.run, daemon=True)
t.start()

input("Press Enter to stop the server...\n")
server.stop()
t.join()
```

---

### `TCPVideoClient`

Connects to a `TCPVideoServer`, receives frames, and displays them.
Reconnects automatically using exponential back-off when the connection drops.

#### Constructor

```python
client = TCPVideoClient(
    host="192.168.1.10",
    port=9999,
    retry_delay=2.0,
    max_retry_delay=30.0,
    max_retries=0,
)
```

| Parameter         | Type    | Default  | Description                                         |
|-------------------|---------|----------|-----------------------------------------------------|
| `host`            | `str`   | —        | Server IP address or hostname (required)            |
| `port`            | `int`   | `9999`   | Server TCP port                                     |
| `retry_delay`     | `float` | `2.0`    | Initial wait between reconnect attempts (seconds)   |
| `max_retry_delay` | `float` | `30.0`   | Upper cap for exponential back-off (seconds)        |
| `max_retries`     | `int`   | `0`      | Max attempts before giving up (`0` = unlimited)     |

#### Methods

| Method   | Returns | Description                                               |
|----------|---------|-----------------------------------------------------------|
| `run()`  | `None`  | Connect and block in the receive/display loop             |
| `stop()` | `None`  | Signal the receive loop to exit cleanly (thread-safe)     |

#### Example — basic client (display only)

```python
from TCPClient import TCPVideoClient

client = TCPVideoClient(host="192.168.1.10", port=9999)
client.run()    # blocks; press ESC or Q to quit
```

#### Example — limited retries

```python
from TCPClient import TCPVideoClient

# try to connect up to 5 times, then give up
client = TCPVideoClient(
    host="192.168.1.10",
    port=9999,
    retry_delay=1.0,
    max_retry_delay=10.0,
    max_retries=5,
)
client.run()
```

---

## Use Case — Object Detection on Received Frames

The client can be subclassed or modified to pass each received frame into an object
detection pipeline instead of (or alongside) displaying it.

The example below uses **YOLOv8** (via [Ultralytics](https://github.com/ultralytics/ultralytics))
to detect objects in every frame received from the server.

```python
"""
object_detection_client.py
--------------------------
Subclass TCPVideoClient to intercept _receive_loop and run YOLOv8 on every frame.

Requirements:
    pip install ultralytics
"""

import cv2
from ultralytics import YOLO
from TCPClient import TCPVideoClient, HEADER_SIZE, HEADER_FMT, RECV_CHUNK
import struct


class DetectionClient(TCPVideoClient):
    """
    TCPVideoClient extended with YOLOv8 object detection.
    Draws bounding boxes and class labels on each received frame before display.
    """

    def __init__(self, model_path: str = "yolov8n.pt", **kwargs):
        """
            constructor — load the YOLO model and forward remaining args to the base class.
        :parameter model_path: path to a YOLOv8 weights file (downloads automatically if not found)
        """
        super().__init__(**kwargs)
        self._model = YOLO(model_path)

    def _receive_loop(self) -> None:
        """
            override the base receive loop to run detection on every decoded frame.
        :return:
        """
        recv_buf = b""

        while self._running:
            # --- read header ---
            recv_buf = self._recv_exactly(recv_buf, HEADER_SIZE)
            if recv_buf is None:
                return

            header_bytes = recv_buf[:HEADER_SIZE]
            recv_buf     = recv_buf[HEADER_SIZE:]
            payload_size = struct.unpack(HEADER_FMT, header_bytes)[0]

            if payload_size == 0 or payload_size > 10 * 1024 * 1024:
                return

            # --- read payload ---
            recv_buf = self._recv_exactly(recv_buf, payload_size)
            if recv_buf is None:
                return

            payload  = recv_buf[:payload_size]
            recv_buf = recv_buf[payload_size:]

            # --- decode frame ---
            frame = self._decode_frame(payload)
            if frame is None:
                continue

            # --- run YOLOv8 detection ---
            results = self._model(frame, verbose=False)

            # draw bounding boxes returned by YOLO onto the frame
            annotated = results[0].plot()

            # display the annotated frame
            cv2.imshow("Detection Stream", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                self.stop()
                return


if __name__ == "__main__":
    client = DetectionClient(
        model_path = "yolov8n.pt",      # nano model — fast inference
        host       = "192.168.1.10",
        port       = 9999,
        max_retries = 0,                 # reconnect indefinitely
    )
    client.run()
```

### Detection pipeline diagram

```
TCPServer (PC1)                      DetectionClient (PC2)
──────────────                       ─────────────────────────────────────────
RealSense camera                     _receive_loop()
  │                                    │
  ▼                                    ├─► _decode_frame()  → BGR np.ndarray
JPEG encode                            │
  │                                    ├─► YOLO(frame)      → Results
  ▼                                    │
pickle + header                        ├─► results[0].plot() → annotated frame
  │                                    │
  └──── TCP ──────────────────────────►└─► cv2.imshow()
```

### Swapping in a different detector

Any detector that accepts a `np.ndarray` (BGR) and returns bounding boxes can be
dropped in at the same point.  Example with **OpenCV DNN** (MobileNet-SSD):

```python
import cv2
import numpy as np

net = cv2.dnn.readNetFromCaffe("deploy.prototxt", "mobilenet_ssd.caffemodel")
CLASSES = ["background", "person", "car", "bottle", ...]   # full list omitted

def detect(frame: np.ndarray) -> np.ndarray:
    """run MobileNet-SSD and draw boxes on frame."""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), 127.5)
    net.setInput(blob)
    detections = net.forward()

    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence < 0.5:
            continue
        idx  = int(detections[0, 0, i, 1])
        box  = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
        x1, y1, x2, y2 = box.astype(int)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f"{CLASSES[idx]}: {confidence:.2f}",
                    (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return frame
```

Replace `results[0].plot()` with `detect(frame)` inside `DetectionClient._receive_loop`.

---

## Wire Protocol

```
┌──────────────────────┬───────────────────────────────────┐
│  Header  (8 bytes)   │  Payload  (variable)              │
│  uint64 payload_size │  pickle( np.ndarray JPEG buffer ) │
└──────────────────────┴───────────────────────────────────┘
```

- Header is a little-endian `unsigned long long` (`struct` format `"Q"`).
- Payload is the result of `pickle.dumps(cv2.imencode(".jpg", frame)[1])`.
- Maximum accepted payload size on the client side: **10 MB** (corrupt-frame guard).

---

## Command-Line Arguments

### TCPServer.py

| Argument   | Default     | Description                       |
|------------|-------------|-----------------------------------|
| `--host`   | `0.0.0.0`   | Bind address                      |
| `--port`   | `9999`      | TCP port                          |
| `--width`  | `640`       | Camera stream width (pixels)      |
| `--height` | `480`       | Camera stream height (pixels)     |
| `--fps`    | `30`        | Camera frame rate                 |

### TCPClient.py

| Argument            | Default       | Description                                      |
|---------------------|---------------|--------------------------------------------------|
| `--host`            | `127.0.0.1`   | Server IP / hostname                             |
| `--port`            | `9999`        | Server TCP port                                  |
| `--retry-delay`     | `2.0`         | Initial reconnect delay (seconds)                |
| `--max-retry-delay` | `30.0`        | Upper cap for back-off delay (seconds)           |
| `--max-retries`     | `0`           | Max reconnect attempts; `0` = unlimited          |