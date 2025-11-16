"""
Shared state for the MCP server
This holds global state, avoiding circular import issues between server and tools
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import Optional
from schemas.schemas import OS_State, Schedule_Decision

# simple memory store for latest OS state and schedule decisions
LATEST_OS_STATE: Optional[OS_State] = None
LATEST_SCHEDULE_DECISION: Optional[Schedule_Decision] = None

