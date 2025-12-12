import asyncio
import logging
import os
import json
from fastmcp import Client
from datetime import datetime
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from typing import List, Dict, Any


# load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# logging - configure to also write to os_connection.log
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "logs", "os_connection.log")
logger = logging.getLogger("scheduler_agent")
logger.setLevel(logging.INFO)

# Remove existing handlers to avoid duplicates
if logger.handlers:
    logger.handlers.clear()

# Add file handler for os_connection.log
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [SCHEDULER_AGENT] %(message)s"))
logger.addHandler(file_handler)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [SCHEDULER_AGENT] %(message)s"))
logger.addHandler(console_handler)

URL_MCP_SERVER = "http://127.0.0.1:8000/mcp"
MODEL_NAME = os.getenv("MODEL_NAME")
MODEL_API_KEY = os.getenv("MODEL_API_KEY")


def extract_tool_result(result) -> dict:
    """
    Extract the actual data from a CallToolResult object.
    Returns the data dict if it's a CallToolResult, otherwise returns the result as-is.
    """
    # Check if it's a CallToolResult object (has structured_content or data attribute)
    if hasattr(result, 'structured_content') and result.structured_content:
        return result.structured_content
    elif hasattr(result, 'data') and result.data:
        return result.data
    elif isinstance(result, dict):
        return result
    else:
        # Try to convert to dict if possible
        try:
            return dict(result) if hasattr(result, '__dict__') else result
        except:
            return {"result": str(result)}


def convert_mcp_tool_to_langchain(mcp_tool) -> Dict[str, Any]:
    # extract input schema and convert to OpenAI parameters format
    input_schema = getattr(mcp_tool, 'inputSchema', None) or {}
    tool_name = getattr(mcp_tool, 'name', 'unknown_tool')
    tool_description = getattr(mcp_tool, 'description', '') or ""
    
    parameters = {
        "type": input_schema.get("type", "object"),
        "properties": input_schema.get("properties", {}),
    }
    
    # add required fields if they exist
    if "required" in input_schema:
        parameters["required"] = input_schema["required"]
    
    # langChain bind_tools expects OpenAI function format
    # format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    tool_dict = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_description,
            "parameters": parameters
        }
    }
    
    return tool_dict


async def scheduler_agent(base_llm, mcp_client: Client):
    # Load system prompt from file
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "scheduler_sys_prompt.md")
    with open(prompt_path, "r") as f:
        prompt_content = f.read()
    system_message = SystemMessage(content=prompt_content)
    human_message = HumanMessage(content=f"Call the get_scheduler_state tool to get the current state of the OS. If needed, use the send_schedule_decision tool to send a schedule decision.")
    messages = [system_message, human_message]
    # invoke the LLM - it may return tool calls
    response = base_llm.invoke(messages)
    
    # handle tool calls if the LLM wants to use tools
    max_iterations = 10  # prevent infinite loops
    iteration = 0
    
    while hasattr(response, 'tool_calls') and response.tool_calls and iteration < max_iterations:
        iteration += 1
        logger.info(f"LLM requested {len(response.tool_calls)} tool call(s)")
        
        # add the assistant message with tool calls to the conversation
        messages.append(response)
        
        # execute each tool call
        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name") or tool_call.name
            tool_args = tool_call.get("args") or getattr(tool_call, "args", {})
            tool_call_id = tool_call.get("id") or getattr(tool_call, "id", f"{tool_name}_{iteration}")
            
            logger.info(f"=== TOOL CALL #{iteration} ===")
            logger.info(f"Tool: {tool_name}")
            logger.info(f"Arguments: {json.dumps(tool_args, indent=2)}")
            
            try:
                # call the tool via MCP client
                tool_result_raw = await mcp_client.call_tool(tool_name, tool_args)
                
                # extract actual data from CallToolResult object
                tool_result = extract_tool_result(tool_result_raw)
                logger.info(f"Tool '{tool_name}' returned: {json.dumps(tool_result, indent=2)}")
                
                # convert tool result to string for ToolMessage
                tool_result_str = json.dumps(tool_result)
                
                # add tool result to messages
                tool_message = ToolMessage(
                    content=tool_result_str,
                    tool_call_id=tool_call_id
                )
                messages.append(tool_message)
            except Exception as e:
                logger.error(f"ERROR calling tool '{tool_name}': {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                tool_message = ToolMessage(
                    content=f"Error: {str(e)}",
                    tool_call_id=tool_call_id
                )
                messages.append(tool_message)
        
        # get the next response from the LLM
        response = base_llm.invoke(messages)
    
    if iteration >= max_iterations:
        logger.warning("Reached maximum tool call iterations")
    
    final_response = response.content if hasattr(response, 'content') else str(response)
    logger.info(f"=== AGENT RESPONSE ===")
    logger.info(f"{final_response}")
    logger.info(f"======================")
    return response.content if hasattr(response, 'content') else str(response)



async def main():
    logger.info("[SCHEDULER AGENT] Agent Connecting to MCP Server")
    client = Client(URL_MCP_SERVER)
    
    async with client:
        logger.info("[SCHEDULER AGENT] MCP Server Connected")
        
        # get tools from MCP server
        mcp_tools = await client.list_tools()
        logger.info(f"[SCHEDULER AGENT] Found {len(mcp_tools)} tools from MCP server")
        
        # convert MCP tools to LangChain format
        langchain_tools = []
        for tool in mcp_tools:
            converted_tool = convert_mcp_tool_to_langchain(tool)
            langchain_tools.append(converted_tool)
        
        # initialize LLM and bind tools
        LLM = ChatGroq(model=MODEL_NAME, api_key=MODEL_API_KEY, temperature=0.0)
        LLM_with_tools = LLM.bind_tools(langchain_tools)
        logger.info("[SCHEDULER AGENT] LLM initialized with tools")

        while True:
            # run agentic logic with tool calling support
            # The agent will call get_scheduler_state itself via tools
            response = await scheduler_agent(LLM_with_tools, client)
            logger.info(f"[SCHEDULER AGENT] Agent Response: {response}")

            # sleep to run every 15 seconds
            await asyncio.sleep(15)


# test
if __name__ == "__main__":
    asyncio.run(main())