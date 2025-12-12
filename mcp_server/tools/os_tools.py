import sys
import os
import logging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from schemas.schemas import Schedule_Decision
from pydantic import ValidationError
from os_connection import move_to_os
import shared_state

# Set up logging to use the same log file as os_connection
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "os_connection.log")
logger = logging.getLogger("os_tools")
logger.setLevel(logging.INFO)
# Only add file handler if it doesn't already exist
if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [OS_TOOLS] %(message)s"))
    logger.addHandler(file_handler)
    logger.addHandler(logging.StreamHandler())


def get_scheduler_state() -> dict:
    """
    Get the current state of the scheduler
    Returns:
        dict: A dict containing the current state of the scheduler
            - "OK": True if the state was retrieved successfully, False otherwise
            - "state": The current state of the scheduler, or None if no state is available
    """
    logger.info("Tool called: get_scheduler_state")
    if shared_state.LATEST_OS_STATE is None:
        logger.warning("No OS state available - returning None")
        return {"OK": True, "state": None}
    
    state_dump = shared_state.LATEST_OS_STATE.model_dump()
    num_processes = len(state_dump.get("ready_processes", []))
    cpu_usage = state_dump.get("cpu_usage", 0.0)
    logger.info(f"Returning OS state: {num_processes} processes in ready queue, CPU usage: {cpu_usage}%")
    return {"OK": True, "state": state_dump}


def send_schedule_decision(decision: dict) -> dict:
    """
    Validate and store the schedule decision made by the agent
    Args:
        decision: A dict containing the schedule decision made by the agent
            - "next_pid": The PID of the next process to be scheduled
            - "reason": The reason for the schedule decision
    Returns:
        dict: A dict containing the result of the operation
            - "OK": True if the schedule decision was validated and stored successfully, False otherwise
            - "error": An error message if the schedule decision was not validated and stored successfully, None otherwise
    """
    logger.info(f"Tool called: send_schedule_decision with decision: {decision}")
    try:
        schedule_decision = Schedule_Decision(**decision) # unpack the decision dict into a Schedule_Decision object
        logger.info(f"Schedule decision validated: PID={schedule_decision.next_pid}, Reason='{schedule_decision.reason}'")
    except ValidationError as ex:
        logger.error(f"Schedule decision validation failed: {ex}")
        return {"OK": False, "error": str(ex)}
    
    shared_state.LATEST_SCHEDULE_DECISION = schedule_decision
    logger.info(f"Stored schedule decision in shared state: PID={schedule_decision.next_pid}")
    
    forward = move_to_os(schedule_decision.model_dump()) # attempt to send to OS
    if forward:
        logger.info(f"Successfully sent schedule decision to OS: PID={schedule_decision.next_pid}")
    else:
        logger.error(f"Failed to send schedule decision to OS: PID={schedule_decision.next_pid}")
    
    return {"OK": forward, "decision": schedule_decision.model_dump()}