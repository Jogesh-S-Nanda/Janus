"""
    Intel RealSense TCP Video Streaming Client
    ==================================================================================================
    Author  :   Jogesh S Nanda
    Date    :   02/04/2026
    Version :   1.0
    Notes   :   Connects to a TCPServer, receives JPEG-encoded frames, decodes them, and
                displays a live video window. Automatically retries the connection on
                network failure using exponential back-off.
                    Architecture : PC1 (server) → TCP → PC2 (this client) → OpenCV window
                    Usage        : python TCPClient.py [--host] [--port]
                                                       [--retry-delay S] [--max-retries N]
                    Wire format  : [ 8-byte uint64 payload_size ]
                                   [ payload_size bytes : pickle(np.ndarray JPEG buffer) ]
                    Keys         : ESC or Q — quit the display window
                    reference    : https://github.com/IntelRealSense/librealsense
    Licence :   MIT License
    ==================================================================================================
"""

import socket
import struct
import pickle
import time
import argparse
import logging
from typing import Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TCPClient")

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
HEADER_FMT     = "Q"                   # must match server — unsigned 64-bit integer
HEADER_SIZE    = struct.calcsize(HEADER_FMT)
RECV_CHUNK     = 4 * 1024              # bytes per recv() call
RECV_TIMEOUT_S = 10.0                  # seconds before an idle connection times out
WINDOW_TITLE   = "RealSense Live Stream"


"""
==================================================================================================
    Class TCPVideoClient : receives and displays a live RealSense video stream from a TCPServer.
    Automatically reconnects after a lost connection using exponential back-off.
==================================================================================================
    functions available are:
        1. run              -   connect to server and start receiving frames
        2. stop             -   signal the receive loop to exit cleanly (thread-safe)
        3. _connect         -   open a TCP connection to the server
        4. _receive_loop    -   receive and display frames until connection drops
        5. _recv_exactly    -   buffer recv() calls until the required byte count is met
        6. _decode_frame    -   deserialize and JPEG-decode a raw payload
        7. _close_socket    -   close the current socket if open
        8. _cleanup         -   release all resources on exit
==================================================================================================
"""
class TCPVideoClient:
    """
    TCP client for live RealSense video streaming.
    version: 1.0
    """

    def __init__(
        self,
        host: str,
        port: int = 9999,
        retry_delay: float = 2.0,
        max_retry_delay: float = 30.0,
        max_retries: int = 0,
    ) -> None:
        """
            class constructor — configure server address and reconnection policy.
        :parameter host:            server IP address or hostname
        :parameter port:            server TCP port
        :parameter retry_delay:     initial wait between reconnection attempts in seconds
        :parameter max_retry_delay: upper cap for exponential back-off in seconds
        :parameter max_retries:     total connection attempts before giving up (0 = unlimited)
        """
        self._host            = host
        self._port            = port
        self._retry_delay     = retry_delay
        self._max_retry_delay = max_retry_delay
        self._max_retries     = max_retries
        self._sock: Optional[socket.socket] = None
        self._running         = False

    def run(self) -> None:
        """
            connect to the server and start receiving frames.
            reconnects automatically on network errors using exponential back-off.
            blocks until stop() is called, max_retries is exceeded, or Ctrl-C is pressed.
        :return:
        """
        self._running = True
        attempt       = 0
        delay         = self._retry_delay

        try:
            while self._running:
                attempt += 1
                if self._max_retries and attempt > self._max_retries:
                    logger.error(
                        "Reached maximum retry limit (%d). Exiting.", self._max_retries
                    )
                    break

                if self._connect():
                    delay = self._retry_delay   # reset back-off after a successful connection
                    self._receive_loop()        # blocks until the connection drops
                else:
                    logger.info("Retrying in %.1f s… (attempt %d)", delay, attempt)
                    time.sleep(delay)
                    # double the delay each failed attempt, capped at max_retry_delay
                    delay = min(delay * 2, self._max_retry_delay)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — exiting.")
        finally:
            self._cleanup()

    def stop(self) -> None:
        """
            signal the receiver loop to exit cleanly.
            safe to call from another thread.
        :return:
        """
        self._running = False

    def _connect(self) -> bool:
        """
            attempt to open a TCP connection to the server.
        :return: True on success, False on any connection error
        """
        self._close_socket()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # disable Nagle for low latency
            sock.settimeout(RECV_TIMEOUT_S)
            sock.connect((self._host, self._port))
            self._sock = sock
            logger.info("Connected to server at %s:%d", self._host, self._port)
            return True
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            logger.warning("Connection failed: %s", exc)
            return False

    def _receive_loop(self) -> None:
        """
            receive frames from the server and display them until the connection
            drops, the user presses ESC/Q, or stop() is called.
        :return:
        """
        recv_buf = b""

        while self._running:
            # read fixed-size header to determine payload length
            recv_buf = self._recv_exactly(recv_buf, HEADER_SIZE)
            if recv_buf is None:
                logger.warning("Connection lost while reading header.")
                return

            header_bytes = recv_buf[:HEADER_SIZE]
            recv_buf     = recv_buf[HEADER_SIZE:]
            payload_size = struct.unpack(HEADER_FMT, header_bytes)[0]

            # sanity check — reject obviously corrupt size values
            if payload_size == 0 or payload_size > 10 * 1024 * 1024:
                logger.warning(
                    "Suspicious payload size (%d bytes) — dropping connection.", payload_size
                )
                return

            # read the full frame payload
            recv_buf = self._recv_exactly(recv_buf, payload_size)
            if recv_buf is None:
                logger.warning("Connection lost while reading payload.")
                return

            payload  = recv_buf[:payload_size]
            recv_buf = recv_buf[payload_size:]

            # decode and display the frame
            frame = self._decode_frame(payload)
            if frame is None:
                continue

            cv2.imshow(WINDOW_TITLE, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):   # ESC or Q — user requested exit
                logger.info("User requested exit.")
                self.stop()
                return

    def _recv_exactly(self, existing_buf: bytes, target_size: int) -> Optional[bytes]:
        """
            accumulate socket data until existing_buf holds at least target_size bytes.
        :parameter existing_buf: data already buffered from previous reads
        :parameter target_size:  minimum number of bytes required in the buffer
        :return:  with at least target_size bytes, or None if the socket closed or errored
        """
        if self._sock is None:
            return None
        buf = existing_buf
        while len(buf) < target_size:
            try:
                chunk = self._sock.recv(RECV_CHUNK)
            except (socket.timeout, OSError) as exc:
                logger.warning("Receive error: %s", exc)
                return None

            if not chunk:
                # server closed the connection cleanly
                return None
            buf += chunk
        return buf

    @staticmethod
    def _decode_frame(payload: bytes) -> Optional[np.ndarray]:
        """
            deserialize a pickle payload and JPEG-decode it to a BGR frame.
        :parameter payload: raw bytes as sent by the server
        :return: BGR NumPy array, or None on decoded failure
        """
        try:
            jpeg_buffer = pickle.loads(payload)
            frame       = cv2.imdecode(jpeg_buffer, cv2.IMREAD_COLOR)
            if frame is None:
                logger.warning("cv2.imdecode returned None — corrupted frame?")
            return frame
        except Exception as exc:
            logger.warning("Frame decode error: %s", exc)
            return None

    def _close_socket(self) -> None:
        """
            close the current socket if it is open.
        :return:
        """
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _cleanup(self) -> None:
        """
            release all resources on exit — closes socket and destroys OpenCV windows.
        :return:
        """
        self._close_socket()
        cv2.destroyAllWindows()
        logger.info("Client shutdown complete.")





def _parse_args() -> argparse.Namespace:
    """
        parse command-line arguments.
    :return: parsed argument namespace
    """
    parser = argparse.ArgumentParser(description="RealSense TCP Video Client")
    parser.add_argument("--host",            default="127.0.0.1", help="Server IP / hostname")
    parser.add_argument("--port",            default=9999,  type=int,   help="Server TCP port (default: 9999)")
    parser.add_argument("--retry-delay",     default=2.0,   type=float, help="Initial reconnect delay in seconds (default: 2)")
    parser.add_argument("--max-retry-delay", default=30.0,  type=float, help="Max reconnect delay in seconds (default: 30)")
    parser.add_argument("--max-retries",     default=0,     type=int,   help="Max connection attempts; 0 = unlimited (default: 0)")
    return parser.parse_args()


if __name__ == "__main__":
    args   = _parse_args()
    client = TCPVideoClient(
        host            = args.host,
        port            = args.port,
        retry_delay     = args.retry_delay,
        max_retry_delay = args.max_retry_delay,
        max_retries     = args.max_retries,
    )
    client.run()
