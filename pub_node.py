import json
import time

import zmq


# Creates the ZeroMQ publisher that streams robot state from the digital twin to any listeners.
def setup_joint_state_publisher(host="127.0.0.1", port=5555):
    """Create a ZeroMQ PUB socket and bind it to the requested endpoint."""
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.setsockopt(zmq.CONFLATE, 1)
    socket.bind(f"tcp://{host}:{port}")
    return context, socket


# Serializes the current joint state into a message that can be consumed by a remote visualization or controller.
def publish_joint_state(socket, time_s, positions):
    """Serialize the current joint state for a subscriber."""
    payload = {
        "time": round(float(time_s), 3),
        "positions": [float(value) for value in positions],
    }
    socket.send_string(json.dumps(payload))


# Closes the network socket so the digital twin stops streaming state cleanly when the sim ends.
def close_joint_state_publisher(context, socket):
    if socket is not None:
        socket.close()
    if context is not None:
        context.term()


# Repeatedly emits the robot's current joint angles to keep external tools synchronized with the twin.
def publish_joint_state_loop(robot, duration=None, rate_hz=50.0, host="127.0.0.1", port=5555):
    """Setup + loop helper for publishing joint angles from a robot object."""
    context, socket = setup_joint_state_publisher(host=host, port=port)

    try:
        period = 1.0 / max(float(rate_hz), 1e-9)
        start_time = time.monotonic()
        while True:
            now = time.monotonic() - start_time
            positions = robot.get_positions()
            publish_joint_state(socket, now, positions)

            if duration is not None and now >= duration:
                break
            time.sleep(period)
    finally:
        close_joint_state_publisher(context, socket)


if __name__ == "__main__":
    class MockRobot:
        # Simple demonstration robot used to validate the published state stream without a full twin.
        def __init__(self):
            self.q = [0.0, 0.0, 0.0]

        # Returns the mock joint positions used by the demo publisher.
        def get_positions(self):
            return self.q

    robot = MockRobot()
    publish_joint_state_loop(robot, duration=1.0, rate_hz=20.0)
