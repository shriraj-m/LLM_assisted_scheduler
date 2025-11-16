# file for all the schemas utilized by the MCP

from pydantic import BaseModel
from typing import Literal, List


class Process(BaseModel):
    pid: int
    state: Literal["running", "sleeping", "zombie", "stopped", "unknown"]
    cpu_burst_ms: int


class OS_State(BaseModel):
    ready_processes: List[Process] # queue of processes
    cpu_usage: float # percentage of CPU usage


class Schedule_Decision(BaseModel):
    next_pid: int
    reason: str # to be populated by the agent
