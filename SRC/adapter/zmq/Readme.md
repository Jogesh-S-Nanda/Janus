# ZMQ RPC Communication — API Reference

ZeroMQ-based publish/subscribe communication for inter-process messaging.
Two implementations are provided with the same public API but different threading models.

---

## Files

| File | Description |
|------|-------------|
| `Server1.py` | Blocking (synchronous) implementation — polls inline on `receive()` |
| `Server2.py` | Non-blocking (threaded) implementation — background thread handles I/O |

---

## Class: `RpcClient`

Available in both `Server1.py` and `Server2.py`.

### Constructor

```python
RpcClient(mode, addr="tcp://localhost:5555")
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `mode` | `str` | `"pub"` to publish, `"sub"` to subscribe |
| `addr` | `str` | ZMQ endpoint address. Default: `"tcp://localhost:5555"` |

**Raises:** `ValueError` if `mode` is not `"pub"` or `"sub"`.

> **Server2.py note:** A background thread is started automatically on construction. The publisher also sleeps 0.2 s after `bind()` to allow the socket to stabilize.

---

### `publish(topic, data)`

Send a message to a topic.

```python
client.publish(topic: str, data: dict)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `topic` | `str` | Topic name |
| `data` | `dict` | Payload, serialized to JSON internally |

**Raises:** `ValueError` if the instance is not in `"pub"` mode.

> **Server1.py:** Sends immediately (blocking).
> **Server2.py:** Writes to a TX buffer; the background thread sends it.

---

### `subscribe(topic)`

Register interest in a topic. Must be called before `receive()`.

```python
client.subscribe(topic: str)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `topic` | `str` | Topic name to filter on |

**Raises:** `ValueError` if the instance is not in `"sub"` mode.

---

### `receive(timeout=0)` *(Server1.py)* / `receive()` *(Server2.py)*

Return the latest received message for the subscribed topic.

**Server1.py signature:**
```python
client.receive(timeout: int = 0) -> dict | None
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `timeout` | `int` | Poll timeout in milliseconds. `0` = return immediately |

**Server2.py signature:**
```python
client.receive() -> tuple[str, dict] | None
```

**Return values:**

| Version | Returns |
|---------|---------|
| Server1.py | `dict` payload of the last message, or `None` if nothing received |
| Server2.py | `(topic: str, data: dict)` tuple, or `None` if nothing received yet |

**Raises:**
- `ValueError` if not in `"sub"` mode.
- `ValueError` / `RuntimeError` if `subscribe()` was not called first.

---

### `close()`

Shut down the socket and ZMQ context cleanly.

```python
client.close()
```

> **Server2.py:** Signals the background thread to stop and joins it before closing.

---

## Usage Examples

### Server1.py — Blocking pub/sub (same process)

```python
from Server1 import RpcClient
import time

publisher = RpcClient("pub")
subscriber = RpcClient("sub")

subscriber.subscribe("sensors")

try:
    while True:
        publisher.publish("sensors", {"temperature": 36.5, "unit": "C"})
        time.sleep(0.5)

        msg = subscriber.receive(timeout=100)   # wait up to 100 ms
        if msg:
            print("Received:", msg)             # {'temperature': 36.5, 'unit': 'C'}

except KeyboardInterrupt:
    publisher.close()
    subscriber.close()
```

### Server1.py — Cross-process (two scripts)

**publisher.py**
```python
from Server1 import RpcClient
import time

pub = RpcClient("pub", addr="tcp://*:5555")
while True:
    pub.publish("cmd", {"joint": 1, "angle": 45.0})
    time.sleep(1)
```

**subscriber.py**
```python
from Server1 import RpcClient

sub = RpcClient("sub", addr="tcp://localhost:5555")
sub.subscribe("cmd")

while True:
    msg = sub.receive(timeout=500)
    if msg:
        print("Command:", msg)   # {'joint': 1, 'angle': 45.0}
```

---

### Server2.py — Non-blocking pub/sub (background thread)

```python
from Server2 import RpcClient
import time

publisher  = RpcClient("pub")
subscriber = RpcClient("sub")

subscriber.subscribe("sensors")

try:
    while True:
        publisher.publish("sensors", {"temperature": 36.5, "unit": "C"})
        time.sleep(0.5)

        result = subscriber.receive()       # non-blocking, returns immediately
        if result:
            topic, data = result
            print(f"[{topic}] {data}")      # [sensors] {'temperature': 36.5, 'unit': 'C'}

except KeyboardInterrupt:
    publisher.close()
    subscriber.close()
```

### Server2.py — Cross-process (two scripts)

**publisher.py**
```python
from Server2 import RpcClient
import time

pub = RpcClient("pub", addr="tcp://*:5555")
while True:
    pub.publish("state", {"x": 1.0, "y": 2.0, "z": 0.5})
    time.sleep(0.1)
```

**subscriber.py**
```python
from Server2 import RpcClient
import time

sub = RpcClient("sub", addr="tcp://localhost:5555")
sub.subscribe("state")

while True:
    result = sub.receive()
    if result:
        topic, data = result
        print(f"[{topic}] x={data['x']} y={data['y']}")
    time.sleep(0.05)    # poll at 20 Hz
```

---

## Choosing Between Server1 and Server2

| | Server1 (Blocking) | Server2 (Threaded) |
|---|---|---|
| Threading | None — polls on `receive()` | Background thread always running |
| `receive()` return | `dict` | `(topic, data)` tuple |
| `receive()` timeout | Configurable (ms) | No timeout — reads buffer instantly |
| Best for | Simple scripts, single-threaded loops | Real-time control loops, GUI apps |
| Latency | Depends on poll timeout | Near real-time (~1 ms poll interval) |

---

## Dependencies

```
pyzmq
```

Install with:
```bash
pip install pyzmq
```

---

**Author:** Jogesh S Nanda
**License:** MIT