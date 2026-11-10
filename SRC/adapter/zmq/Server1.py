"""
    Code for RPC communication using ZMQ protocol.
    ==================================================================================================
    Author  :   Jogesh S Nanda
    Date    :   27/03/2026
    Version :   1.0
    Notes   :   code is made for creating RPC communication using ZMQ protocol.
        Libraries used: ZeroMQ
                    reference : https://zeromq.org/
    Licence:   MIT License
    ==================================================================================================
"""
import zmq
import json
import time



"""
============================================================================
    Class RpcClient :
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
    class for controlling the robot using ZMQ RPC protocol.
    version: 2.0.0
    Author: Jogesh S Nanda
    """
    def __init__(self, mode, addr = "tcp://localhost:5555"):
        """
        class constructor
        :parameter mode: "pub" or "sub"
        :parameter addr: address of the server
        """
        self.context = zmq.Context()
        self.mode = mode
        self.addr = addr
        self.message = None
        self.subscribes = False

        if mode == "pub":
            #  acts as a publisher
            self.socket = self.context.socket(zmq.PUB)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.bind(addr)

        elif mode == "sub":
            #  acts as a subscriber
            self.socket = self.context.socket(zmq.SUB)
            self.socket.setsockopt(zmq.LINGER, 0)
            #self.socket.setsockopt(zmq.SUBSCRIBE, b"") # subscribe to all topics
            self.socket.connect(addr)

        else:
            raise ValueError("mode must be 'pub' or 'sub'")


        #  Wait for the next request from a client
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)

    def close(self):
        """
            function to close the socket.
        """
        self.socket.close()
        self.context.term()

    def publish(self, Topic:str, data: dict):
        """
            publish a message to a topic.
        :parameter Topic:  name (str)
        :parameter data: message (dict)
        :return:
        """
        if self.mode != "pub":
            raise ValueError("mode must be 'pub'")

        msg = json.dumps(data).encode("utf-8")
        topic = Topic.encode("utf-8")

        # send it as a multipart message
        self.socket.send_multipart([topic, msg])

    def subscribe(self, Topic:str):
        """
            function to subscribe to a topic.
        :parameter Topic: name (str)
        :return:
        """
        if self.mode != "sub":
            raise ValueError("mode must be 'sub'")

        self.socket.setsockopt_string(zmq.SUBSCRIBE, Topic)
        self.subscribes = True

    def receive(self, timeout=0):
        """
            function to receive a message after subscribing to a topic.
        :parameter timeout: timeout in milliseconds
        :return: message in JSON format
        """
        if self.mode != "sub":
            raise ValueError("mode must be 'sub'")

        if not self.subscribes:
            raise ValueError("subscribe() must be called before receive()")

        event = dict(self.poller.poll(timeout))
        if self.socket in event:
            # decode the message when a message is received
            topic_bytes, msg_bytes = self.socket.recv_multipart()

            # decode the topic and message
            topic = topic_bytes.decode("utf-8")
            self.message = json.loads(msg_bytes.decode("utf-8"))

        # returns the last message received
        return self.message




def main():
    """
    example use case for the ZMQControl class.
    """
    # create client instances
    client01 = RpcClient("pub")
    client02 = RpcClient("sub")

    # subscribe to a topic
    client02.subscribe("topic")

    try:
        while True:
            # publish a message
            client01.publish("topic", {"data": "hello"})
            time.sleep(1)

            # receive a message
            print(client02.receive())


    except KeyboardInterrupt:
        # close the socket
        client01.close()
        client02.close()
        print("Exiting...")


if __name__ == "__main__":
    # run the main function
    main()
