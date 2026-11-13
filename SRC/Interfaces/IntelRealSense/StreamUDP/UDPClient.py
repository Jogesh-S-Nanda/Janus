"""
    Intel RealSense UDP Video Streaming Client
    ==================================================================================================
    Author  :   Jogesh S Nanda
    Date    :   02/04/2026
    Version :   1.0
    Notes   :   Connects to a UDPServer by sending a HELLO registration datagram, then
                receives fragmented JPEG frames, reassembles them, decodes and displays
                a live video window.  Out-of-order and duplicate datagrams are handled
                gracefully; incomplete frames are silently discarded.
                    Architecture : PC1 (server) → UDP → PC2 (this client) → OpenCV window
                    Usage        : python UDPClient.py [--host HOST] [--port PORT]
                                                       [--listen-port PORT]
                    Wire format  : per datagram —
                                   [ frame_id : 4 B ][ chunk_idx : 2 B ][ total_chunks : 2 B ]
                                   [ chunk payload  : ≤ MAX_CHUNK_BYTES ]
                    Keys         : ESC or Q — quit the display window
                    reference    : https://github.com/IntelRealSense/librealsense
    Licence :   MIT License
    ==================================================================================================
"""
import socket
import struct
import argparse
import logging
from collections import defaultdict
from typing import Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt= "%H:%M:%S",
)
logger = logging.getLogger("UDPClient")

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
HELLO_MSG       = b"HELLO"             # must match server
HEADER_FMT      = "!IHH"              # must match server
HEADER_SIZE     = struct.calcsize(HEADER_FMT)
RECV_BUF_BYTES  = 65536               # recv buffer — large enough for one datagram
RECV_TIMEOUT_S  = 5.0                 # seconds of silence before logging a warning
WINDOW_TITLE    = "RealSense UDP Live Stream"

# discard buffered chunks for frames older than this many frames behind the latest
FRAME_BUFFER_DEPTH = 5


"""
==================================================================================================
    Class UDPVideoClient : receives and displays a live RealSense video stream from a UDPServer.
    Sends a HELLO datagram to register with the server, then reassembles fragmented JPEG frames
    and displays them using OpenCV.  Incomplete frames are silently dropped.
==================================================================================================
    functions available are:
        1. run              -   register with server and start receiving frames
        2. stop             -   signal the receive loop to exit cleanly (thread-safe)
        3. _open_socket     -   create and bind the receive socket
        4. _register        -   send HELLO datagram to the server
        5. _receive_loop    -   receive datagrams, reassemble frames, and display them
        6. _try_assemble    -   attempt to decode a fully received frame
        7. _decode_frame    -   JPEG-decode a reassembled byte string to a BGR array
        8. _cleanup         -   release all resources on exit
==================================================================================================
"""
class UDPVideoClient:
    """
    UDP client for live RealSense video streaming.
    version: 1.0
    """

    def __init__(
        self,
        host:        str = "127.0.0.1",
        port:        int = 9999,
        listen_port: int = 9998,
    ) -> None:
        """
            class constructor — configure server address and local receive port.
        :parameter host:        IP address or hostname of the UDPServer
        :parameter port:        UDP port the server is listening on
        :parameter listen_port: local port this client binds to for receiving datagrams
        """
        self._server_addr  = (host, port)
        self._listen_port  = listen_port
        self._sock: Optional[socket.socket] = None
        self._running      = False

        # reassembly buffer: frame_id → { chunk_idx → bytes }
        self._frame_buf: dict = defaultdict(dict)
        self._latest_frame_id = -1

    def run(self) -> None:
        """
            open the socket, register with the server, and start receiving frames.
            blocks until ESC/Q is pressed or stop() is called.
        :return:
        """
        self._running = True
        self._open_socket()
        self._register()

        try:
            self._receive_loop()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — exiting.")
        finally:
            self._cleanup()

    def stop(self) -> None:
        """
            signal the receive loop to exit cleanly.
            safe to call from another thread.
        :return:
        """
        self._running = False

    def _open_socket(self) -> None:
        """
            create and bind the UDP receive socket.
        :return:
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # increase receive buffer to reduce datagram drops under burst traffic
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        sock.settimeout(RECV_TIMEOUT_S)
        sock.bind(("0.0.0.0", self._listen_port))
        self._sock = sock
        logger.info("Listening on port %d", self._listen_port)

    def _register(self) -> None:
        """
            send a HELLO datagram to the server to register this client's address.
            the server will begin streaming to the source address of this packet.
        :return:
        """
        if self._sock is None:
            return
        self._sock.sendto(HELLO_MSG, self._server_addr)
        logger.info("Sent HELLO to server at %s:%d", *self._server_addr)

    def _receive_loop(self) -> None:
        """
            receive datagrams from the server, reassemble frames, and display them.
            exits when the user presses ESC/Q or stop() is called.
        :return:
        """
        while self._running:
            # receive one UDP datagram
            if self._sock is None:
                break
            try:
                data, _ = self._sock.recvfrom(RECV_BUF_BYTES)
            except socket.timeout:
                logger.debug("No datagram received within %.1f s — still waiting…", RECV_TIMEOUT_S)
                continue
            except OSError as exc:
                logger.warning("Receive error: %s", exc)
                break

            # parse the fixed-size header
            if len(data) < HEADER_SIZE:
                logger.debug("Datagram too short to contain header — discarded.")
                continue

            frame_id, chunk_idx, total_chunks = struct.unpack(
                HEADER_FMT, data[:HEADER_SIZE]
            )
            chunk_payload = data[HEADER_SIZE:]

            # store chunk in the reassembly buffer
            self._frame_buf[frame_id][chunk_idx] = chunk_payload

            # track the highest frame_id seen so far
            if frame_id > self._latest_frame_id:
                self._latest_frame_id = frame_id

            # evict chunks for frames too far behind to avoid memory growth
            stale_ids = [
                fid for fid in self._frame_buf
                if fid < self._latest_frame_id - FRAME_BUFFER_DEPTH
            ]
            for fid in stale_ids:
                del self._frame_buf[fid]

            # attempt to decode if all chunks for this frame have arrived
            if len(self._frame_buf[frame_id]) == total_chunks:
                frame = self._try_assemble(frame_id, total_chunks)
                del self._frame_buf[frame_id]     # free reassembly memory

                if frame is not None:
                    cv2.imshow(WINDOW_TITLE, frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):       # ESC or Q
                        logger.info("User requested exit.")
                        self.stop()

    def _try_assemble(self, frame_id: int, total_chunks: int) -> Optional[np.ndarray]:
        """
            reassemble all chunks for a frame and JPEG-decode the result.
        :parameter frame_id:     identifier of the frame to reassemble
        :parameter total_chunks: expected number of chunks
        :return: BGR NumPy array, or None on decode failure
        """
        chunks = self._frame_buf.get(frame_id, {})
        if len(chunks) != total_chunks:
            # frame is incomplete — silently discard
            return None

        # concatenate chunks in order
        jpeg_bytes = b"".join(chunks[i] for i in range(total_chunks))
        return self._decode_frame(jpeg_bytes)

    @staticmethod
    def _decode_frame(jpeg_bytes: bytes) -> Optional[np.ndarray]:
        """
            JPEG-decode a raw byte string into a BGR frame.
        :parameter jpeg_bytes: raw JPEG bytes
        :return: BGR NumPy array, or None on decode failure
        """
        try:
            buf   = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is None:
                logger.warning("cv2.imdecode returned None — corrupted frame?")
            return frame
        except Exception as exc:
            logger.warning("Frame decode error: %s", exc)
            return None

    def _cleanup(self) -> None:
        """
            release all resources on exit — closes socket and destroys OpenCV windows.
        :return:
        """
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        cv2.destroyAllWindows()
        logger.info("Client shutdown complete.")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    """
        parse command-line arguments.
    :return: parsed argument namespace
    """
    parser = argparse.ArgumentParser(description="RealSense UDP Video Client")
    parser.add_argument("--host",        default="127.0.0.1", help="Server IP / hostname")
    parser.add_argument("--port",        default=9999, type=int, help="Server UDP port (default: 9999)")
    parser.add_argument("--listen-port", default=9998, type=int, help="Local receive port (default: 9998)")
    return parser.parse_args()


if __name__ == "__main__":
    args   = _parse_args()
    client = UDPVideoClient(
        host        = args.host,
        port        = args.port,
        listen_port = args.listen_port,
    )
    client.run()