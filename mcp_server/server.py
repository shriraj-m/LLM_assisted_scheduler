import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastmcp import FastMCP
from tools.os_tools import get_scheduler_state, send_schedule_decision
from os_connection import start_listener
import logging

logger = logging.getLogger("mcp")

def main():
    logger.info("[MCP] Starting MCP server")

    # start listenin for OS
    start_listener()

    # initialize the mcp server
    mcp = FastMCP(name="llm_scheduler_mcp")

    # register tools
    tools = [get_scheduler_state, send_schedule_decision]
    for tool in tools:
        mcp.tool(tool)

    # run the server
    mcp.run(transport="http", port=8000)


if __name__ == "__main__":
    main()