import socket
import json 
import threading
import logging
import pathlib
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from typing import Optional, Callable

from schemas.schemas import OS_State, Process
import shared_state

# Logging configuration
LOG_FILE = "mcp_server\logs\os_connection.log"
logging.basicConfig(
    level=logging.INFO,  
    format="%(asctime)s [%(levelname)s] %(message)s",  
    handlers=[
        logging.FileHandler(LOG_FILE),  
        logging.StreamHandler()  
    ]
)
logger = logging.getLogger("os_connection")


# create functions to connect to the XV86 OS (socket connections)
OS_HOST = "127.0.0.1"  # localhost
OS_LISTEN_PORT = 5050  # port for OS communication
OS_DECISION_PORT = 5051  # port for OS communication

def start_listener(on_update: Optional[Callable[[dict], None]] = None):
    """
    Listens for telemetry from the OS.
    Starts a thread if found
    Args:
        on_update: A function to call when the OS state is updated
    """
    # create a TCP socket for inter-process communication
    # AF_INET = IPv4, SOCK_STREAM = reliable, connection-based (TCP)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((OS_HOST, OS_LISTEN_PORT))
    server_socket.listen(1)

    logger.info(f"[OS_CONNECTION] Listening for OS telemetry on {OS_HOST}:{OS_LISTEN_PORT}")

    def listen_loop():
        """
        Loop to listen for telemetry from the OS
        This runs continuously in a background thread, waiting for OS updates
        """
        nonlocal server_socket
        while True:
            # block until the OS connects to send telemetry data
            connection, _ = server_socket.accept()
            with connection:
                buffer = b""
                while True:
                    # receive data in chunks of up to 4096 bytes
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                # skip if no data was received
                if not buffer:
                    continue
                try:
                    # decode the bytes to a string and parse JSON
                    data = json.loads(buffer.decode("utf-8"))
                    logger.info(f"[OS_CONNECTION] Received telemetry: {data}")
                    # update the global state with latest telemetry
                    set_latest_os_state(data)
                    if on_update:
                        on_update(data)
                except Exception as ex:
                    logger.error(f"[OS_CONNECTION] Error processing telemetry: {ex}")
                    import traceback
                    logger.error(f"[OS_CONNECTION] Traceback: {traceback.format_exc()}")
    
    # start the listener in a daemon thread (will exit when main program exits)
    thread = threading.Thread(target=listen_loop, daemon=True)
    thread.start()


def set_latest_os_state(state: dict):
    """
    Set the latest OS state by converting it to OS_State model and storing in shared_state
    Args:
        state: A dict containing the latest OS state from the OS simulation
    """
    try:
        # Convert the incoming state dict to OS_State model
        # Map "ready_queue" to "ready_processes" and convert process states
        ready_processes = []
        for proc in state.get("ready_queue", []):
            # Map "ready" state to "running" since Process schema doesn't have "ready"
            # These are processes ready to be scheduled/run
            process_state = proc.get("state", "unknown")
            if process_state == "ready":
                process_state = "running"  # Ready processes are ready to run
            
            ready_processes.append(Process(
                pid=proc.get("pid"),
                state=process_state,
                cpu_burst_ms=proc.get("cpu_burst_ms", 0)
            ))
        
        # Create OS_State object
        os_state = OS_State(
            ready_processes=ready_processes,
            cpu_usage=state.get("cpu_usage", 0.0)
        )
        
        # Update shared state
        shared_state.LATEST_OS_STATE = os_state
        logger.info(f"[OS_CONNECTION] Set latest OS state: {os_state.model_dump()}")
    except Exception as ex:
        logger.error(f"[OS_CONNECTION] Error converting OS state: {ex}")
        import traceback
        logger.error(f"[OS_CONNECTION] Traceback: {traceback.format_exc()}")


def move_to_os(decision: dict) -> bool:
    """
    Send the schedule decision to the OS
    Args:
        decision: A dict containing the schedule decision
    Returns:
        bool: True if the schedule decision was sent successfully, False otherwise
    """
    next_pid = decision.get("next_pid", "unknown")
    reason = decision.get("reason", "no reason provided")
    logger.info(f"Attempting to send schedule decision to OS: PID={next_pid}, Reason='{reason}'")
    
    try:
        # create a TCP client socket to send data TO the OS
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((OS_HOST, OS_DECISION_PORT))
        payload = {"type": "decision", "payload": decision}
        payload_json = json.dumps(payload)
        client_socket.sendall(payload_json.encode("utf-8"))
        # close the connection after sending
        client_socket.close()
        logger.info(f"Successfully sent schedule decision to OS simulation: PID={next_pid}")
        return True
    except Exception as ex:
        logger.error(f"Error sending schedule decision to OS: {ex}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False