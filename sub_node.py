import zmq
import json
import time

def run_subscriber():
    # 1. Initialize ZMQ context and socket
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    
    # Drop old frames to keep parsing real-time data
    socket.setsockopt(zmq.CONFLATE, 1)
    
    # Connect to the local publisher node
    socket.connect("tcp://127.0.0.1:5555")
    
    # Subscribe to ALL messages (empty string acts as a wildcard)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    print("Subscriber Node started. Listening on port 5555...")

    try:
        while True:
            # Receive data string (blocking call until a message arrives)
            message_string = socket.recv_string()
            
            # Parse it back into a Python dictionary
            data = json.loads(message_string)
            
            print(f"Received at t={data['time']}: Positions -> {[round(p, 3) for p in data['positions']]}")
            
    except KeyboardInterrupt:
        print("\nShutting down Subscriber Node safely...")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    run_subscriber()
