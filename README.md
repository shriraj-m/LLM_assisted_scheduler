# LLM-Assisted Process Scheduler

## Overview

This project is a difficult extra credit assignment for our Operating Systems class at Florida Polytechnic University. Completion of this project and report counts as the final exam grade! We are tasked to implement an intelligent process scheduler, using a Large Language Model (LLM) to assist in making scheduling decisions. Instead of relying on traditional hard-coded scheduling algorithms, the system lets an AI agent analyze the current operating system state and determine which process should be moved forward.

---

## Project Goal

The goal of this project is to explore how Large Language Models can be used to make operating system scheduling decisions and if they make an impact in comparison to traditional methods. Traditional schedulers use fixed algorithms like Round Robin or Shortest Job First. Our approach allows the LLM to dynamically which algorithm fits the best based on the current system state.


## Table of Contents
- [Phase 1: MCP Server & Agent Integration](#phase-1-mcp-server-and-llm-agent)
- [Phase 2: Ollama Integration](#phase-2-os-simulation)
- [Installation and Usage](#installation-and-usage)

---

By giving the LLM access to information about ready processes and CPU usage, it can determine which scheduling algorithm would work best for the current situation. For example, if there are many short processes waiting, it might choose Shortest Job First. If fairness is more important, it might choose Round Robin.

This project demonstrates the potential for AI-assisted systems programming and explores a new way of thinking about process scheduling.

---

## Phase 1: MCP Server & Agent Integration
Phase 1 focuses on building the MCP server infrastructure and the LLM-powered scheduler agent.

### System Architecture

```
+------------------+       TCP Socket       +------------------+       HTTP/MCP       +------------------+
|                  |  (Port 5050 - state)   |                  |    (Port 8000)       |                  |
|  OS Simulation   | ---------------------> |    MCP Server    | <------------------> |  Scheduler Agent |
|                  | <--------------------- |                  |                      |      (LLM)       |
|                  |  (Port 5051 - decision)|                  |                      |                  |
+------------------+                        +------------------+                      +------------------+
```

1. The OS Simulation sends telemetry data (process info, CPU usage) to the MCP Server.
2. The MCP Server stores this state and exposes it through MCP tools.
3. The Scheduler Agent connects to the MCP Server and uses tools to get state and send decisions.
4. Decisions flow back through the MCP Server to the OS Simulation.


### Data Schemas

We defined Pydantic models to validate and structure all data flowing through the system. The `Process` model represents a single process with its PID, state, and CPU burst time. The `OS_State` model holds the ready queue and CPU usage. The `Schedule_Decision` model captures the agent's choice of which process to run next and its reasoning.

```python
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
```

### MCP Server

The MCP server uses FastMCP to expose two tools that the LLM can call. It also starts a TCP listener to receive telemetry from the OS simulation.

```python
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
```

### OS Connection Module

The OS connection module handles all TCP socket communication. The `start_listener` function creates a server socket that listens for incoming telemetry data on port 5050. When the data arrives, it'll parse the JSON and update the shared state.

```python
def start_listener(on_update: Optional[Callable[[dict], None]] = None):
    """
    Listens for telemetry from the OS.
    Starts a thread if found
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((OS_HOST, OS_LISTEN_PORT))
    server_socket.listen(1)

    logger.info(f"[OS_CONNECTION] Listening for OS telemetry on {OS_HOST}:{OS_LISTEN_PORT}")
```

The `move_to_os` function sends scheduling decisions back to the OS on port 5051:

```python
def move_to_os(decision: dict) -> bool:
    """
    Send the schedule decision to the OS
    """
    next_pid = decision.get("next_pid", "unknown")
    reason = decision.get("reason", "no reason provided")
    logger.info(f"Attempting to send schedule decision to OS: PID={next_pid}, Reason='{reason}'")
    
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((OS_HOST, OS_DECISION_PORT))
        payload = {"type": "decision", "payload": decision}
        payload_json = json.dumps(payload)
        client_socket.sendall(payload_json.encode("utf-8"))
        client_socket.close()
        logger.info(f"Successfully sent schedule decision to OS simulation: PID={next_pid}")
        return True
    except Exception as ex:
        logger.error(f"Error sending schedule decision to OS: {ex}")
        return False
```

### MCP Tools

The tools module defines the two functions that the LLM can call. The `get_scheduler_state` function returns the current OS state from shared memory:

```python
def get_scheduler_state() -> dict:
    """
    Get the current state of the scheduler
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
```

The `send_schedule_decision` function validates the decision and forwards it to the OS:

```python
def send_schedule_decision(decision: dict) -> dict:
    """
    Validate and store the schedule decision made by the agent
    """
    logger.info(f"Tool called: send_schedule_decision with decision: {decision}")
    try:
        schedule_decision = Schedule_Decision(**decision)
        logger.info(f"Schedule decision validated: PID={schedule_decision.next_pid}, Reason='{schedule_decision.reason}'")
    except ValidationError as ex:
        logger.error(f"Schedule decision validation failed: {ex}")
        return {"OK": False, "error": str(ex)}
    
    shared_state.LATEST_SCHEDULE_DECISION = schedule_decision
    forward = move_to_os(schedule_decision.model_dump())
    return {"OK": forward, "decision": schedule_decision.model_dump()}
```

### Scheduler Agent

The scheduler agent is the core of the system. It uses LangChain with Groq LLMs to make decisions. The agent connects to the MCP server and converts MCP tools to LangChain format:

```python
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
```

The agent runs in a loop, calling tools and processing responses. It handles multiple tool calls in sequence:

```python
while hasattr(response, 'tool_calls') and response.tool_calls and iteration < max_iterations:
    iteration += 1
    logger.info(f"LLM requested {len(response.tool_calls)} tool call(s)")
    
    messages.append(response)
    
    for tool_call in response.tool_calls:
        tool_name = tool_call.get("name") or tool_call.name
        tool_args = tool_call.get("args") or getattr(tool_call, "args", {})
        
        logger.info(f"=== TOOL CALL #{iteration} ===")
        logger.info(f"Tool: {tool_name}")
        
        # call the tool via MCP client
        tool_result_raw = await mcp_client.call_tool(tool_name, tool_args)
        tool_result = extract_tool_result(tool_result_raw)
        
        tool_message = ToolMessage(
            content=json.dumps(tool_result),
            tool_call_id=tool_call_id
        )
        messages.append(tool_message)
    
    response = base_llm.invoke(messages)
```

### System Prompt

The system prompt instructs the LLM on how to make scheduling decisions. It describes available tools and common scheduling algorithms that we've learned in class:

```markdown
## PURPOSE
You are a **scheduler agent**. You are responsible for scheduling processes on a computer based on the Operating System information.

## SCHEDULING ALGORITHMS
Here are common scheduling algorithms you can use to make decisions:

**Shortest Job First (SJF)**: Select the process with the smallest CPU burst time. This minimizes average waiting time but requires knowing burst times in advance.

**First Come First Served (FCFS)**: Schedule processes in the order they arrive. Simple but can lead to convoy effect where short processes wait behind long ones.

**Round Robin (RR)**: Give each process a time slice and cycle through all ready processes. Prevents starvation and provides fair CPU time distribution.

**Priority Scheduling**: Schedule processes based on priority levels. Higher priority processes run first.
```

---

## Phase 2: Ollama Integration
Direct LLM Intervention

## Scheduling Components

This section documents the custom scheduling hooks added to xv6 and the host-side tooling used to interact with them. Fill in the details as you finalize each component.

---

### `int get_runqueue(int *pids, int max)`
**Location:** `proc.c`  

**Purpose:**  
This gets the pids of the current running processes'.

**Parameters:**  
This function takes in an empty array and the max number of processes.

**Returns:**  
This function populates the empty array and returns the number of values it entered into the array.

---

### `int sys_get_runqueue(void)`
**Location:** `sysproc.c`  

**Purpose:**  
This is the system call that enables users to communicate with the kernel and get the running processes'. 

**Returns:**  
This populates the array the user passes into the userside function and calls the get_runqueue function to get the pids.

---

### `int schedule_next_kernel(int pid)`
**Location:** `proc.c`  

**Purpose:**  
This function is meant to intervene in the scheduler with a selected pid.

**Parameters:**  
pid is the pid of the process the scheduler should run next. Once decided the scheduler will prioritize this process.

**Returns:**  
The function retruns whether the schedule was successful or not.

---

### `int sys_schedule_next(void)`
**Location:** `sysproc.c`  

**Purpose:**  
This function returns 0 if it was successful and -1 if not.

**Parameters:**  
This takes the pid the user passed into their argument to the kernel side to effectively allow a user to select the next pid to schedule.

**Returns:**  
This function returns 0 if it was successful and -1 if not.



---

### `void scheduler(void)`
**Location:** `kernel/proc.c`  

**Purpose:**  
This is the modified scheduler that is responsible for handling AI inputs to the OS.
  
**Behavior Summary:**  
In the scheduler the nextpid selected by the LLM will be given a timeslice where it will be allowed to run. In the case a nextpid is selected the scheduler will prioritize running the process. In any case where the LLM has not selected a pid the LLM will run in round robin as to not freeze up the scheduling process.

---

### `worker.c`
**Purpose:**  
This program runs a simple function that just prints values to the console while it is alive.

---

### `schedd.c`
**Purpose:**  
This program opens the interface between the llm and the scheduler. As the program runs it will output the current processes using the get_runqueue system call and schedule the next appropriate job using the pids provided by the LLM in the order they were entered.

This program also spawns 3 worker functions to demonstrate the processes in action.

---

### `terminal.py`
**Purpose:**  
This program connects to the serial output of xv6 to read the OS output, feed it to an LLM, and input the results back into the scheduler.

**Requirements:**  
To run this program requires OLLAMA to be installed and active.

The program currently uses gemma3n but this can be changed.

**In one terminal launch the xv6 instance:**
```bash
make qemu-nox
```

once this has been done you will have to note down the location the serial output can be found at.  
ex `/dev/pts/7` you will use this number as an argument for terminal.py

**In another terminal run Command:**
```bash
pip install -r requirements.txt
python3 terminal.py 7
```

---

## Installation and Usage

### Requirements

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### Environment Setup

Create a `.env` file in the project root with your Groq API credentials:

```
MODEL_NAME=your_model_name
MODEL_API_KEY=your_api_key
```

### Running the System

1. Start the MCP server:
```bash
python mcp_server/server.py
```

2. Start the OS simulation:
```bash
python scripts/simulate_os_data.py
```

3. Start the scheduler agent:
```bash
python agents/scheduler_agent.py
```

### Project Structure

```
LLM_assisted_scheduler/
├── agents/
│   ├── scheduler_agent.py      # LLM agent that makes scheduling decisions
│   └── prompts/
│       └── scheduler_sys_prompt.md  # System prompt for the agent
├── mcp_server/
│   ├── server.py               # MCP server entry point
│   ├── os_connection.py        # TCP socket communication with OS
│   ├── shared_state.py         # Global state storage
│   └── tools/
│       └── os_tools.py         # MCP tools for LLM to call
├── schemas/
│   └── schemas.py              # Pydantic data models
├── scripts/
│   ├── simulate_os_data.py     # OS telemetry simulator
│   └── test_mcp_client.py      # MCP client test script
├── requirements.txt
└── README.md
```

