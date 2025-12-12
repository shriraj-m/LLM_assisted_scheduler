import serial
from time import sleep
import random

import socket
import json

import argparse
from ollama import Client



def main():
    prompt = "Given the following PIDs and their burst times, generate an optimal scheduling order using the Shortest Job First (SJF) algorithm.\n\nPIDs and Burst Times Jobs with a higher priority should be scheduled first:\n"

    response_format = "\n\nReturn only the scheduling order as a list of pids separated by spaces. Do not provide explanations or any additional information."

    client = Client(host='http://localhost:11434')  # default Ollama

    response = client.chat(
        model='gemma3n',
        messages=[
            {'role': 'user', 'content': 'Hello from Python!'}
        ]
    )

    print(response['message']['content'])

    HOST = "127.0.0.1"
    PORT = 5050

    def send_to_os_connection(payload: dict):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))

        data = json.dumps(payload).encode("utf-8")
        s.sendall(data)
        s.close()

    # Example telemetry
    parser = argparse.ArgumentParser(description="xv6 terminal interface")
    parser.add_argument(
        "value",
        type=int,
        help="Example positional argument (e.g., an integer like 7)"
    )

    args = parser.parse_args()

    # Use args.value wherever needed
    # e.g., pass to sys_schedule_next, set a PID, etc.
    ser = serial.Serial(f'/dev/pts/{args.value}', 9600, timeout=1)
    ser.write(b"schedd\n")
    while True:
        line = ser.readline().decode('utf-8').rstrip()
        if "MCP" in line:
            numbers = eval(line.split("MCP_IN: ")[1].strip())
            print(numbers)
            if len(numbers) == 0:
                ser.write(b"\n")
                continue
            telemetry = {
                "pids": numbers,
                "bursts": [random.randint(15, 25) for _ in numbers],
                "priorities": [random.randint(1, 10) for _ in numbers]
            }
            print("Telemetry:", telemetry)
            response = client.chat(
            model='gemma3n',
            messages=[
                {'role': 'user', 'content': prompt + json.dumps(telemetry) + response_format}
                ]
            )

            print("Ollama Response:", response['message']['content'].strip())
            ser.write((response['message']['content'] + "\n").encode('utf-8'))
        if "worker" in line:
            print(line)

if __name__ == "__main__":
    main()