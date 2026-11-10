"""
    Code for RpcClient - ZMQ PUB/SUB wrapper with latest-value semantics
    ==================================================================================================
    Author  :   Jogesh S Nanda
    Date    :   16/01/2025
    Version :   3.0.0
    Notes   :   code is made for a ZMQ PUB/SUB client using pyzmq library.
                    PUB side  : publish() stores the most recent (topic, data) in a single slot.
                                The background thread sends it whenever the slot is replaced.
                                Old values are silently overwritten, so the publisher can run
                                at any rate without back-pressure.
                    SUB side  : background thread caches every incoming message in _rx_buffer.
                                receive() returns the latest cached value without clearing it,
                                so the subscriber always reads the most recent value.
                    Both sides are rate-independent: a fast publisher does not stall a slow
                    subscriber, and a fast subscriber does not block on a slow publisher.
    Licence:   MIT License
    ==================================================================================================
"""
import zmq
import json
import time
import threading



"""
============================================================================
    RcClient
============================================================================
    contains the following functions,
    1. publish      - to publish a message to a topic.
    2. subscribe    - to subscribe to a topic.
    3. receive  - to receive a message after subscribing to a topic.
    4. close    - to close the socket.
============================================================================
"""
class RpcClient:
    """
    ZMQ PUB/SUB client with latest-value semantics.
    version: 3.0.0
    """
    def __init__(self, mode, addr="tcp://localhost:5555"):
        """
        :param mode: "pub" or "sub"
        :param addr: ZMQ address to bind (pub) or connect (sub)
        """
        self.context = zmq.Context()
        self.mode    = mode
        self.addr    = addr

        self._lock    = threading.Lock()
        self._running = True

        if mode == "pub":
            self.socket = self.context.socket(zmq.PUB)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.bind(addr)
            self._latest_tx = None          # (topic, data) slot – latest only
            time.sleep(0.2)                 # allow socket to finish binding

        elif mode == "sub":
            self.socket = self.context.socket(zmq.SUB)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.connect(addr)
            self._rx_buffer  = None         # latest received (topic, data)
            self.subscribed  = False

        else:
            raise ValueError("mode must be 'pub' or 'sub'")

        self.thread = threading.Thread(target=self._thread_loop_, daemon=True)
        self.thread.start()


    """
    ============================================
    PRIVATE FUNCTIONS
    ============================================
    """
    def _thread_loop_(self):
        """
            background thread for sending and receiving messages.
        :return: None
        """
        if self.mode == "pub":
            last_sent = None

            # send messages until the thread is stopped
            while self._running:
                # parallel read of latest_tx and _latest_sent
                with self._lock:
                    pending = self._latest_tx

                # only transmit when publish() has posted something new
                if pending is not None and pending is not last_sent:
                    topic, data = pending
                    self.socket.send_multipart(
                        [topic.encode(), json.dumps(data).encode()]
                    )
                    last_sent = pending

                else:
                    # idle: avoid busy-spin
                    time.sleep(0.001)

        elif self.mode == "sub":
            poller = zmq.Poller()
            poller.register(self.socket, zmq.POLLIN)

            # poll for messages until the thread is stopped
            while self._running:
                events = dict(poller.poll(1))   # 1 ms timeout

                # only process messages that arrived in the meantime
                if self.socket in events:
                    topic, msg = self.socket.recv_multipart()
                    with self._lock:
                        self._rx_buffer = (topic.decode(), json.loads(msg.decode()))

        else:
            # invalid mode raised earlier
            raise ValueError("mode must be 'pub' or 'sub'")


    """
    ============================================
    PUBLIC FUNCTIONS
    ============================================
    """
    def publish(self, topic: str, data: dict):
        """
            publish a message to a topic.
        :parameter topic: topic name (str)
        :parameter data: message payload (dict)
        :return: None
        """
        if self.mode != "pub":
            raise ValueError("Run the class in publisher mode 'pub'")

        # store the latest value (running in background thread)
        with self._lock:
            self._latest_tx = (topic, data)     # overwrite – latest wins

    def subscribe(self, topic: str):
        """
        Subscribes to a specific topic in subscriber mode.

        This method sets the subscription to the provided topic. It is only
        valid when the instance is running in subscriber mode ('sub').
        Attempts to call this method in a different mode will result in an
        error.

        :param topic: The topic to subscribe to.
        :return: None
        """
        if self.mode != "sub":
            # raise an error if the class instance is not in subscriber mode
            raise ValueError("Run the class in subscriber mode 'sub'")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        self.subscribed = True

    def receive(self):
        """
        Return the latest received (topic, data) tuple, or None if no
        message has arrived yet.  The buffer is NOT cleared on read, so
        calling receive() repeatedly returns the same value until a new
        message arrives.

        :return: (topic, data)
        """
        if self.mode != "sub":
            raise ValueError("Run the class in subscriber mode 'sub'")
        if not self.subscribed:
            raise RuntimeError("Call subscribe() first")

        # return the latest received value (running in background thread)
        with self._lock:
            return self._rx_buffer

    def close(self):
        """
        Closes the running thread and associated resources.

        This method halts the execution of the thread, ensuring it stops gracefully
        within the specified timeout. It also closes the socket and releases the
        context. Useful for properly shutting down the system and freeing up resources.

        :return: None
        """
        self._running = False
        self.thread.join(timeout=2.0)
        self.socket.close()
        self.context.term()




def main():
    """
        test the RpcClient class.
    :return: None
    """
    pub = RpcClient("pub")
    sub = RpcClient("sub")
    sub.subscribe("topic")

    try:
        t = 0
        while True:
            pub.publish("topic", {"data": "hello", "t": t})
            t += 1
            time.sleep(1)
            print(sub.receive())

    except KeyboardInterrupt:
        pub.close()
        sub.close()
        print("Exiting...")


if __name__ == "__main__":
    main()