# DH AG95 Gripper — API Reference

Python interface for the **DH Robotics AG95** gripper over Modbus RTU (RS-485),
using the `minimalmodbus` library.

---

## File

| File | Description |
|------|-------------|
| `GripperAG95.py` | `Gripper` class — full control and feedback for the AG95 gripper |

---

## Hardware Setup

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Timeout | 1 s |
| Protocol | Modbus RTU (Function code 3 = read, 6 = write) |

Connect the gripper via a USB-to-RS485 adapter. On Linux the port is typically
`/dev/ttyUSB0`; on Windows it is `COM3`, `COM4`, etc.

---

## Class: `Gripper`

### Constructor

```python
Gripper(port, slaveID)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `port` | `str` | Serial port name, e.g. `"/dev/ttyUSB0"` or `"COM3"` |
| `slaveID` | `int` | Modbus slave address of the gripper (default on device: `1`) |

Opens the serial connection and configures the port settings immediately.

---

## API Functions

### `activate()`

Initialize and enable the gripper. Must be called once after connecting.

```python
gripper.activate()
```

Writes `0xA5` to register `0x0100`. Prints `"Gripper activated"` on success.

---

### `check_state()`

Read the initialization state of the gripper.

```python
gripper.check_state() -> int
```

| Return | Meaning |
|--------|---------|
| `1` | Gripper is initialized and ready |
| `0` | Gripper is not initialized (or communication error) |

---

### `open()`

Fully open the gripper (position = 1000).

```python
gripper.open()
```

Writes `0x03E8` (1000) to position register `0x0103`.

---

### `close()`

Fully close the gripper (position = 0).

```python
gripper.close()
```

Writes `0x0000` to position register `0x0103`.

---

### `set_gripping_force(force=20)`

Set the gripping force as a percentage.

```python
gripper.set_gripping_force(force: int = 20)
```

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `force` | `int` | 20 – 100 | `20` | Gripping force in % |

Values are clamped to the range `[20, 100]` before writing to register `0x0101`.

---

### `set_gripping_position(position=0)`

Move the gripper to an absolute position.

```python
gripper.set_gripping_position(position: int = 0)
```

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `position` | `int` | 0 – 1000 | `0` | Target position (0 = fully closed, 1000 = fully open) |

Values are clamped to `[0, 1000]` before writing to register `0x0103`.

---

### `get_gripping_position()`

Read the current finger position.

```python
gripper.get_gripping_position() -> int | None
```

Returns the raw position value from register `0x0202` in the range `[0, 1000]`.
Returns `None` on communication error.

---

### `get_gripper_state()`

Read the current motion/grip state of the fingers.

```python
gripper.get_gripper_state() -> tuple[int, str]
```

| Return code | String | Meaning |
|-------------|--------|---------|
| `0` | `"In motion"` | Fingers are currently moving |
| `1` | `"Reached position"` | Fingers reached target; no object detected |
| `2` | `"Object caught"` | Fingers stopped due to object contact |
| `3` | `"Object dropped"` | Object was caught but has since been dropped |
| `4` | `"Error"` | Unexpected register value |

Reads from register `0x0201`.

---

### `object_grip()`

Close the gripper and hold at the contact position (force-hold grip).

```python
gripper.object_grip()
```

1. Calls `close()` to start closing motion.
2. Polls `get_gripper_state()` until motion stops.
3. Reads the contact position with `get_gripping_position()`.
4. Writes that position back with `set_gripping_position()` to hold the object.

Use this when gripping objects of unknown size.

---

### `scale(value, v_min=0, v_max=1000)`

Clamp and convert a value for Modbus transmission.

```python
gripper.scale(value: int, v_min: int = 0, v_max: int = 1000) -> str | int
```

| Parameter | Description |
|-----------|-------------|
| `value` | Input integer |
| `v_min` | Lower clamp bound (default `0`) |
| `v_max` | Upper clamp bound (default `1000`) |

Returns `hex(value)` if within range, otherwise returns `v_max` or `v_min` as integer.
Used internally by `set_gripping_force()` and `set_gripping_position()`.

---

### `read_register(address)`

Low-level Modbus register read (function code 3).

```python
gripper.read_register(address: int) -> int | None
```

Returns the integer register value, or `None` on error.

---

### `write_register(address, value)`

Low-level Modbus register write (function code 6).

```python
gripper.write_register(address: int, value: int)
```

Prints an error message on failure. No return value.

---

### `debug()`

Enable verbose Modbus communication logging.

```python
gripper.debug()
```

Sets `AG95.debug = True` on the underlying `minimalmodbus.Instrument`.

---

## Register Map

| Register | Access | Description |
|----------|--------|-------------|
| `0x0100` | Write | Activation command (`0xA5` = activate) |
| `0x0101` | Write | Gripping force (20–100 %) |
| `0x0103` | Write | Target position (0–1000) |
| `0x0200` | Read | Initialization state (1 = ready) |
| `0x0201` | Read | Motion/grip state (0–3) |
| `0x0202` | Read | Actual finger position (0–1000) |

---

## Usage Examples

### Basic open / close

```python
from GripperAG95 import Gripper
import time

gripper = Gripper("/dev/ttyUSB0", slaveID=1)

gripper.activate()
time.sleep(1)                       # wait for activation

if gripper.check_state() == 1:
    gripper.set_gripping_force(50)  # 50% force

    gripper.open()
    time.sleep(2)

    gripper.close()
    time.sleep(2)
```

---

### Move to a specific position

```python
from GripperAG95 import Gripper
import time

gripper = Gripper("/dev/ttyUSB0", slaveID=1)
gripper.activate()
time.sleep(1)

gripper.set_gripping_force(30)

# half open
gripper.set_gripping_position(500)
time.sleep(1)

pos = gripper.get_gripping_position()
print(f"Current position: {pos}")   # e.g. 498
```

---

### Grip an object (unknown size)

```python
from GripperAG95 import Gripper
import time

gripper = Gripper("/dev/ttyUSB0", slaveID=1)
gripper.activate()
time.sleep(1)

gripper.set_gripping_force(60)

gripper.open()
time.sleep(1)

# Place object between fingers, then grip
gripper.object_grip()

code, label = gripper.get_gripper_state()
print(f"State: [{code}] {label}")
# State: [2] Object caught

# Release
gripper.open()
```

---

### Poll state in a control loop

```python
from GripperAG95 import Gripper
import time

gripper = Gripper("/dev/ttyUSB0", slaveID=1)
gripper.activate()
time.sleep(1)

gripper.set_gripping_force(40)
gripper.close()

# Wait until motion completes
while True:
    code, label = gripper.get_gripper_state()
    pos = gripper.get_gripping_position()
    print(f"[{label}]  pos={pos}")

    if code != 0:           # not "In motion"
        break
    time.sleep(0.05)

if code == 2:
    print("Object secured.")
elif code == 1:
    print("Nothing gripped — fingers reached closed position.")
```

---

### Integration with UR5

```python
from SRC.UR5.ur_control import UR5Control
from SRC.UR5.ur_feedback import UR5Feedback
from SRC.Interfaces.GripperDH.GripperAG95 import Gripper
import numpy as np, time

ROBOT_IP = "192.168.1.100"
GRIPPER_PORT = "/dev/ttyUSB0"

ctrl    = UR5Control(ROBOT_IP)
fb      = UR5Feedback(ROBOT_IP)
gripper = Gripper(GRIPPER_PORT, slaveID=1)

ctrl.connect()
fb.connect()
gripper.activate()
time.sleep(1)

# Move robot to pick position
pick_pose = np.array([0.4, -0.2, 0.3, 0.0, 3.14, 0.0])
ctrl.moveP(pick_pose)

# Grip object
gripper.set_gripping_force(50)
gripper.object_grip()

code, label = gripper.get_gripper_state()
print(f"Gripper: {label}")

# Move to place position
place_pose = np.array([0.4, 0.2, 0.3, 0.0, 3.14, 0.0])
ctrl.moveP(place_pose)

# Release
gripper.open()
time.sleep(0.5)

ctrl.stop()
ctrl.disconnect()
fb.disconnect()
```

---

## Startup Sequence

```
Gripper(port, slaveID) → activate() → check_state() → set_gripping_force() → [open / close / set_gripping_position / object_grip]
```

Always call `activate()` first and verify `check_state() == 1` before issuing motion commands.

---

## Dependencies

```
minimalmodbus
pyserial
```

Install with:
```bash
pip install minimalmodbus pyserial
```

---

**Author:** Jogesh S Nanda
**License:** MIT