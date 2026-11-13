"""
    Intel RealSense TCP Video Streaming Server
    ==================================================================================================
    Author  :   Jogesh S Nanda
    Date    :   02/04/2026
    Version :   1.0
    Notes   :   Captures color frames from an Intel RealSense camera and streams them to a
                connected TCP client over the network. Supports multiple sequential client
                connections — after a client disconnects, the server waits for the next one
                without restarting the camera.
                    Architecture : PC1 (server) — RealSense → encode JPEG → TCP → PC2 (client)
                    Usage        : python TCPServer.py [--host] [--port]
                                                       [--width W] [--height H] [--fps]
                    Wire format  : [ 8-byte uint64 payload_size ]
                                   [ payload_size bytes : pickle(np.ndarray JPEG buffer) ]
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
import threading
from typing import Optional

import cv2
import numpy as np
import pyrealsense2 as rs

# ---------------------------------------------------------------------------
# logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TCPServer")

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
HEADER_FMT      = "Q"                  # unsigned 64-bit integer (payload size)
HEADER_SIZE     = struct.calcsize(HEADER_FMT)
JPEG_QUALITY    = 80                   # JPEG encode quality (0–100)
SEND_TIMEOUT_S  = 5.0                  # seconds before a sending is considered hung
ACCEPT_TIMEOUT_S = 1.0                 # accept poll interval so stop_event can be checked


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
        """
            context manager entry — starts the pipeline.
        :return: self
        """
        self.start()
        return self

    def __exit__(self, *_) -> None:
        """
            context manager exit — stops the pipeline.
        :return:
        """
        self.stop()


"""
==================================================================================================
    Class TCPVideoServer : streams RealSense color frames to one TCP client at a time.
    After a client disconnects the server waits for the next connection automatically.
==================================================================================================
    functions available are:
        1. run              -   start camera, bind socket, enter the main serve loop
        2. stop             -   signal the serve loop to exit cleanly (thread-safe)
        3. _bind_server     -   create and bind the server socket
        4. _accept_client   -   wait for an incoming connection (non-blocking poll)
        5. _stream_to_client-   send JPEG frames to the connected client
        6. _shutdown        -   release camera and socket resources
==================================================================================================
"""
class TCPVideoServer:
    """
    TCP server for live RealSense video streaming.
    version: 1.0
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9999,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
    ) -> None:
        """
            class constructor — configure network and camera parameters.
        :parameter host:    bind address ("0.0.0.0" accepts connections on all interfaces)
        :parameter port:    TCP port to listen on
        :parameter width:   RealSense color stream width in pixels
        :parameter height:  RealSense color stream height in pixels
        :parameter fps:     desired camera frame rate
        """
        self._host          = host
        self._port          = port
        self._camera        = RealSenseCamera(width, height, fps)
        self._server_socket: Optional[socket.socket] = None
        self._stop_event    = threading.Event()

    def run(self) -> None:
        """
            start the camera, bind the TCP socket, and enter the main serve loop.
            blocks until a keyboard interrupt is received or stop() is called.
        :return:
        """
        self._camera.start()
        self._bind_server()

        logger.info("Server listening on %s:%d — press Ctrl-C to quit.", self._host, self._port)

        try:
            while not self._stop_event.is_set():
                client_sock, addr = self._accept_client()
                if client_sock is None:
                    continue    # accept timed out — loop back and check stop_event
                logger.info("Client connected: %s", addr)
                self._stream_to_client(client_sock, addr)
                logger.info("Client %s disconnected. Waiting for next connection…", addr)
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

    def _bind_server(self) -> None:
        """
            create, configure, and bind the server socket.
            SO_REUSEADDR is set to allow quick restart after a crash.
        :return:
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # timeout on acceptance so we can check stop_event periodically
        sock.settimeout(ACCEPT_TIMEOUT_S)
        sock.bind((self._host, self._port))
        sock.listen(1)
        self._server_socket = sock
        logger.info("Bound to %s:%d", self._host, self._port)

    def _accept_client(self) -> tuple:
        """
            wait up to ACCEPT_TIMEOUT_S for an incoming TCP connection.
        :return: (client_socket, address) on success, or (None, None) on timeout
        """
        if self._server_socket is None:
            return None, None
        try:
            return self._server_socket.accept()
        except socket.timeout:
            return None, None

    def _stream_to_client(self, client_sock: socket.socket, addr: tuple) -> None:
        """
            continuously send JPEG-encoded frames to the connected client.
            exits when the connection drops, a scent error occurs, or stop() is called.

            wire format per frame:
                [ 8-byte header : payload size ] [ pickle (JPEG buffer) ]

        :parameter client_sock: connected client socket
        :parameter addr:        client address tuple (ip, port)
        :return:
        """
        client_sock.settimeout(SEND_TIMEOUT_S)
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

        try:
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

                # serialize and prepend 8-byte size header
                payload = pickle.dumps(buffer)
                header  = struct.pack(HEADER_FMT, len(payload))

                # send header + payload in one call to reduce fragmentation
                client_sock.sendall(header + payload)

        except (BrokenPipeError, ConnectionResetError, socket.timeout) as exc:
            logger.warning("Connection to %s lost: %s", addr, exc)
        except OSError as exc:
            logger.error("Socket error while streaming to %s: %s", addr, exc)
        finally:
            try:
                client_sock.close()
            except OSError:
                pass

    def _shutdown(self) -> None:
        """
            release all resources — stops the camera and closes the server socket.
        :return:
        """
        logger.info("Shutting down server…")
        self._camera.stop()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
        logger.info("Server shutdown complete.")





def _parse_args() -> argparse.Namespace:
    """
        parse command-line arguments.
    :return: parsed argument namespace
    """
    parser = argparse.ArgumentParser(description="RealSense TCP Video Server")
    parser.add_argument("--host",   default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port",   default=9999, type=int, help="TCP port (default: 9999)")
    parser.add_argument("--width",  default=640,  type=int, help="Camera width  (default: 640)")
    parser.add_argument("--height", default=480,  type=int, help="Camera height (default: 480)")
    parser.add_argument("--fps",    default=30,   type=int, help="Camera FPS    (default: 30)")
    return parser.parse_args()


if __name__ == "__main__":
    args   = _parse_args()
    server = TCPVideoServer(
        host   = args.host,
        port   = args.port,
        width  = args.width,
        height = args.height,
        fps    = args.fps,
    )
    server.run()
