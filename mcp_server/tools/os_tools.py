import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from schemas.schemas import Schedule_Decision
from pydantic import ValidationError
from os_connection import move_to_os
import shared_state


def get_scheduler_state() -> dict:
    """
    Get the current state of the scheduler
    Returns:
        dict: A dict containing the current state of the scheduler
            - "OK": True if the state was retrieved successfully, False otherwise
            - "state": The current state of the scheduler, or None if no state is available
    """
    if shared_state.LATEST_OS_STATE is None:
        return {"OK": True, "state": None}
    return {"OK": True, "state": shared_state.LATEST_OS_STATE.model_dump()}


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
    try:
        schedule_decision = Schedule_Decision(**decision) # unpack the decision dict into a Schedule_Decision object
    except ValidationError as ex:
        return {"OK": False, "error": str(ex)}
    shared_state.LATEST_SCHEDULE_DECISION = schedule_decision
    forward = move_to_os(schedule_decision.model_dump()) # attempt to send to OS
    return {"OK": forward, "decision": schedule_decision.model_dump()}