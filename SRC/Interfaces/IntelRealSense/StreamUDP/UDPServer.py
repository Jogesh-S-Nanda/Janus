"""
    Intel RealSense UDP Video Streaming Server
    ==================================================================================================
    Author  :   Jogesh S Nanda
    Date    :   02/04/2026
    Version :   1.0
    Notes   :   Captures color frames from an Intel RealSense camera and streams them to a
                registered UDP client over the network.  Because UDP datagrams are limited
                to ~65 KB each, every JPEG frame is split into fixed-size chunks before
                sending; the client reassembles them before decoding.
                    Architecture : PC1 (server) — RealSense → JPEG → fragment → UDP → PC2 (client)
                    Usage        : python UDPServer.py [--host HOST] [--port PORT]
                                                       [--width W] [--height H] [--fps FPS]
                    Registration : server waits for a HELLO datagram from the client before
                                   streaming starts — no need to hard-code the client IP.
                    Wire format  : per datagram —
                                   [ frame_id : 4 B ][ chunk_idx : 2 B ][ total_chunks : 2 B ]
                                   [ chunk payload  : ≤ MAX_CHUNK_BYTES ]
                    reference    : https://github.com/IntelRealSense/librealsense
    Licence :   MIT License
    ==================================================================================================
"""
import socket
import struct
import time
import argparse
import logging
import threading
from typing import Optional

import cv2
import numpy as np
import pyrealsense2 as rs

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt= "%H:%M:%S",
)
logger = logging.getLogger("UDPServer")

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
HELLO_MSG       = b"HELLO"             # registration packet sent by the client
HEADER_FMT      = "!IHH"              # big-endian: frame_id(u32) chunk_idx(u16) total_chunks(u16)
HEADER_SIZE     = struct.calcsize(HEADER_FMT)
MAX_CHUNK_BYTES = 60000               # max payload bytes per UDP datagram (well below 65507 limit)
JPEG_QUALITY    = 80                  # JPEG encode quality (0–100)
HELLO_TIMEOUT_S = 1.0                 # poll interval while waiting for client registration


"""
==================================================================================================
    Class RealSenseCamera : thin wrapper around the pyrealsense2 pipeline.
    Opens the camera once and exposes a simple read() interface.
==================================================================================================
    functions available are:
        1. start        -   start the RealSense pipeline
        2. stop         -   stop the RealSense pipeline
        3. read         -   capture and return the next BGR color frame
        4. __enter__    -   context manager entry (calls start)
        5. __exit__     -   context manager exit  (calls stop)
==================================================================================================
"""
class RealSenseCamera:
    """
    Wrapper for the Intel RealSense color stream.
    version: 1.0
    """

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30) -> None:
        """
            class constructor — configure stream resolution and frame rate.
        :parameter width:   color stream width in pixels
        :parameter height:  color stream height in pixels
        :parameter fps:     desired camera frame rate
        """
        self._width    = width
        self._height   = height
        self._fps      = fps
        self._pipeline: Optional[rs.pipeline] = None

    def start(self) -> None:
        """
            start the pyrealsense2 pipeline with the configured stream settings.
        :return:
        """
        try:
            pipeline = rs.pipeline()
            cfg      = rs.config()
            cfg.enable_stream(
                rs.stream.color,
                self._width, self._height,
                rs.format.bgr8,
                self._fps,
            )
            pipeline.start(cfg)
            self._pipeline = pipeline
            logger.info(
                "RealSense pipeline started (%dx%d @ %d fps)",
                self._width, self._height, self._fps,
            )
        except Exception as exc:
            self._pipeline = None
            raise RuntimeError(f"Failed to start RealSense pipeline: {exc}") from exc

    def stop(self) -> None:
        """
            stop the pyrealsense2 pipeline and release camera resources.
        :return:
        """
        if self._pipeline is not None:
            try:
                self._pipeline.stop()
                logger.info("RealSense pipeline stopped.")
            except Exception as exc:
                logger.warning("Error stopping pipeline: %s", exc)
            finally:
                self._pipeline = None

    def read(self) -> Optional[np.ndarray]:
        """
            capture the next color frame from the camera.
        :return: BGR NumPy array, or None if no frame is available
        """
        if self._pipeline is None:
            return None
        try:
            frames      = self._pipeline.wait_for_frames(timeout_ms=2000)
            color_frame = frames.get_color_frame()
            if not color_frame:
                return None
            return np.asanyarray(color_frame.get_data())
        except Exception as exc:
            logger.warning("Frame capture error: %s", exc)
            return None

    def __enter__(self) -> "RealSenseCamera":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.stop()


"""
==================================================================================================
    Class UDPVideoServer : streams RealSense color frames to a registered UDP client.
    Waits for a HELLO datagram from the client to learn its address before streaming.
    Each JPEG frame is split into MAX_CHUNK_BYTES fragments and reassembled by the client.
==================================================================================================
    functions available are:
        1. run                  -   start camera, bind socket, enter the main serve loop
        2. stop                 -   signal the serve loop to exit cleanly (thread-safe)
        3. _bind_socket         -   create and bind the UDP socket
        4. _wait_for_client     -   block until a HELLO datagram is received
        5. _stream_to_client    -   send fragmented JPEG frames to the registered client
        6. _send_frame          -   fragment and send one frame to the client
        7. _shutdown            -   release camera and socket resources
==================================================================================================
"""
class UDPVideoServer:
    """
    UDP server for live RealSense video streaming.
    version: 1.0
    """

    def __init__(
        self,
        host:   str = "0.0.0.0",
        port:   int = 9999,
        width:  int = 640,
        height: int = 480,
        fps:    int = 30,
    ) -> None:
        """
            class constructor — configure network and camera parameters.
        :parameter host:    bind address ("0.0.0.0" accepts on all interfaces)
        :parameter port:    UDP port to listen on
        :parameter width:   RealSense color stream width in pixels
        :parameter height:  RealSense color stream height in pixels
        :parameter fps:     desired camera frame rate
        """
        self._host       = host
        self._port       = port
        self._camera     = RealSenseCamera(width, height, fps)
        self._sock: Optional[socket.socket] = None
        self._stop_event = threading.Event()
        self._frame_id   = 0              # rolling frame counter for reassembly on client

    def run(self) -> None:
        """
            start the camera, bind the UDP socket, and enter the main serve loop.
            blocks until a keyboard interrupt is received or stop() is called.
        :return:
        """
        self._camera.start()
        self._bind_socket()

        logger.info("Server listening on %s:%d — waiting for client HELLO…", self._host, self._port)

        try:
            while not self._stop_event.is_set():
                # wait for client registration; loops back if timeout fires
                client_addr = self._wait_for_client()
                if client_addr is None:
                    continue
                logger.info("Client registered: %s — starting stream.", client_addr)
                self._stream_to_client(client_addr)
                logger.info("Stream ended. Waiting for next client HELLO…")

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — shutting down.")
        finally:
            self._shutdown()

    def stop(self) -> None:
        """
            signal the serve loop to exit cleanly.
            safe to call from another thread.
        :return:
        """
        self._stop_event.set()

    def _bind_socket(self) -> None:
        """
            create and bind the UDP socket.
        :return:
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # increase send buffer to reduce datagram drops at high frame rates
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        sock.settimeout(HELLO_TIMEOUT_S)
        sock.bind((self._host, self._port))
        self._sock = sock
        logger.info("Bound to %s:%d", self._host, self._port)

    def _wait_for_client(self) -> Optional[tuple]:
        """
            block until a HELLO datagram arrives, then return the client's address.
            returns None on timeout so the caller can check stop_event.
        :return: (ip, port) of the registered client, or None on timeout
        """
        try:
            data, addr = self._sock.recvfrom(64)
            if data.strip() == HELLO_MSG:
                return addr
            logger.debug("Received unexpected datagram from %s — ignored.", addr)
            return None
        except socket.timeout:
            return None

    def _stream_to_client(self, client_addr: tuple) -> None:
        """
            continuously capture frames and send them to the registered client.
            exits when stop() is called, the camera fails, or a send error occurs.
        :parameter client_addr: (ip, port) of the destination client
        :return:
        """
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

        while not self._stop_event.is_set():
            frame = self._camera.read()
            if frame is None:
                logger.warning("Dropped frame (camera returned None).")
                time.sleep(0.01)
                continue

            # encode frame to JPEG
            success, buffer = cv2.imencode(".jpg", frame, encode_params)
            if not success:
                logger.warning("JPEG encoding failed; skipping frame.")
                continue

            try:
                self._send_frame(buffer.tobytes(), client_addr)
            except OSError as exc:
                logger.warning("Send error to %s: %s — stopping stream.", client_addr, exc)
                return

    def _send_frame(self, jpeg_bytes: bytes, client_addr: tuple) -> None:
        """
            split one JPEG frame into fixed-size chunks and send each as a UDP datagram.
            header per datagram: frame_id(u32) | chunk_idx(u16) | total_chunks(u16)
        :parameter jpeg_bytes:  raw JPEG bytes for the frame
        :parameter client_addr: destination (ip, port)
        :return:
        """
        # split the JPEG payload into chunks that fit within MAX_CHUNK_BYTES
        chunks = [
            jpeg_bytes[i : i + MAX_CHUNK_BYTES]
            for i in range(0, len(jpeg_bytes), MAX_CHUNK_BYTES)
        ]
        total = len(chunks)

        for idx, chunk in enumerate(chunks):
            header  = struct.pack(HEADER_FMT, self._frame_id, idx, total)
            self._sock.sendto(header + chunk, client_addr)

        # advance the frame counter; wrap at 2^32
        self._frame_id = (self._frame_id + 1) % (2 ** 32)

    def _shutdown(self) -> None:
        """
            release all resources — stops the camera and closes the socket.
        :return:
        """
        logger.info("Shutting down server…")
        self._camera.stop()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        logger.info("Server shutdown complete.")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    """
        parse command-line arguments.
    :return: parsed argument namespace
    """
    parser = argparse.ArgumentParser(description="RealSense UDP Video Server")
    parser.add_argument("--host",   default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port",   default=9999, type=int, help="UDP port (default: 9999)")
    parser.add_argument("--width",  default=640,  type=int, help="Camera width  (default: 640)")
    parser.add_argument("--height", default=480,  type=int, help="Camera height (default: 480)")
    parser.add_argument("--fps",    default=30,   type=int, help="Camera FPS    (default: 30)")
    return parser.parse_args()


if __name__ == "__main__":
    args   = _parse_args()
    server = UDPVideoServer(
        host   = args.host,
        port   = args.port,
        width  = args.width,
        height = args.height,
        fps    = args.fps,
    )
    server.run()