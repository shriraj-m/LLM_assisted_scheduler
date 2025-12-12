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