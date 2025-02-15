import requests
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from typing import Dict, Any
from pydantic import BaseModel  # Import Pydantic
from pathlib import Path, PureWindowsPath

app = FastAPI()

# CORS configuration (replace with your actual origins in production)
origins = ["http://localhost", "http://127.0.0.1"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Restrict in production
    allow_headers=["*"],  # Restrict in production
)

# Pydantic model for input validation
class RunTaskRequest(BaseModel):
    task: str

def bake_cake(number_people: int, flavour: str):
    return {"message": f"Your {flavour} cake for {number_people} is now ready."}

    
def sort_contacts(input_location: str, output_location: str):

    output_location= os.path.abspath(output_location)
    if not os.path.exists(input_location):
        raise HTTPException(status_code=404, detail=f"Input file {input_location} does not exist.")

    try:
        with open(input_location, 'r', encoding='utf-8') as file:
            contacts = json.load(file)

        contacts.sort(
            key=lambda c: (c.get("last_name", "").lower(), c.get("first_name", "").lower())
        )

        with open(output_location, 'w', encoding='utf-8') as file:
            json.dump(contacts, file, indent=4)

        return {"status": "success", "message": f"Contacts sorted and saved to {output_location}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sorting contacts: {e}")

def write_recent_log_lines(input_location: str, output_location: str):
    if not os.path.exists(input_location):
        raise HTTPException(status_code=404, detail=f"Logs directory {input_location} does not exist.")

    try:
        log_files = sorted(Path(input_location).glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)[:10]

        with open(output_location, 'w', encoding='utf-8') as output_file:
            for log_file in log_files:
                with open(log_file, 'r', encoding='utf-8') as file:
                    first_line = file.readline().strip()
                    output_file.write(first_line + "\n")

        return {
            "status": "success",
            "message": f"First lines of 10 most recent logs saved to {output_location}.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing log files: {e}")
    
BAKE_CAKE = {
    "type": "function",
    "function": {
        "name": "bake_cake",
        "description": "Bakes a cake with the specified flavour for a given number of people.",
        "parameters": {
            "type": "object",
            "properties": {
                "number_people": {"type": "integer", "description": "Number of people"},
                "flavour": {"type": "string", "description": "Cake flavour"}
            },
            "required": ["number_people", "flavour"],
            "additionalProperties": False,
        },
    },
}

SORT_CONTACTS = {
    "type": "function",
    "function": {
        "name": "sort_contacts",
        "description": """
            Sorts a list of contacts in JSON format.
            Input:
                - input_location (string): The path to the JSON file containing the contacts.
                - output_location (string): The path where the sorted contacts should be written.
            Output:
                - A JSON object with a "status" field (string) indicating "Success" or "Error",
                  and an "output_file_destination" field (string) containing the path to the sorted contacts file.
        """,
        "parameters": {
            "type": "object",
            "properties": {
                "input_location": {"type": "string", "description": "Input file path"},
                "output_location": {"type": "string", "description": "Output file path"},
            },
            "required": ["input_location", "output_location"],
            "additionalProperties": False,
        },
    },
}

WRITE_RECENT_LOG_LINES = {
    "type": "function",
    "function": {
        "name": "write_recent_log_lines",
        "description": """
            Reads the first line of the 10 most recent .log files from the /data/logs/ directory
            and writes them to /data/logs-recent.txt in descending order of recency.
            Input:
                - input_location (string): The directory containing the .log files.
                - output_location (string): The path to the output file where the recent log lines should be written.
            Output:
                - A JSON object with a "status" field (string) indicating "Success" or "Error",
                  and an "output_file_destination" field (string) containing the path to the output file.
        """,
        "parameters": {
            "type": "object",
            "properties": {
                "input_location": {"type": "string", "description": "Directory path containing log files"},
                "output_location": {"type": "string", "description": "Output file path"},
            },
            "required": ["input_location", "output_location"],
            "additionalProperties": False,
        },
    },
}

AIPROXY_Token = os.getenv("AIPROXY_TOKEN")

tools = [BAKE_CAKE, SORT_CONTACTS, WRITE_RECENT_LOG_LINES]

def query_gpt(user_input: str, tools: list[Dict[str, Any]]) -> Dict[str, Any]:
    if not AIPROXY_Token:
        raise HTTPException(status_code=500, detail="AIPROXY_TOKEN environment variable is missing")
    print("AIPROXY_Token:", AIPROXY_Token) 

    try:
        response = requests.post(
            "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AIPROXY_Token}"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_input}
                ],
                "tools": tools,
                "tool_choice": "auto"
            },
            verify=False  # Use with caution in production!
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling GPT API: {e}")
        raise HTTPException(status_code=500, detail=f"GPT API error: {e}")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON response from GPT API: {e}")
        raise HTTPException(status_code=500, detail=f"Invalid JSON response: {e}")
    except Exception as e:
        print(f"A general error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"A general error occurred: {e}")

FUNCTIONS = {
    "bake_cake": bake_cake,
    "sort_contacts": sort_contacts,
    "write_recent_log_lines": write_recent_log_lines,
}

@app.post("/run")  # Changed to POST
async def run(task_request: RunTaskRequest):  # Use Pydantic model
    task = task_request.task.strip()
    if not task:
        raise HTTPException(status_code=400, detail="Task cannot be empty")

    try:
        query = query_gpt(task, tools)
        print(query)

        tool_calls = query.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])

        if tool_calls:
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                arguments_json = tool_call["function"].get("arguments", "{}")

                try:
                    arguments = json.loads(arguments_json)
                except json.JSONDecodeError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON arguments: {e}")

                if function_name in FUNCTIONS:
                    func = FUNCTIONS[function_name]
                    try:
                        output = func(**arguments)
                        return output
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=f"Error calling function: {e}")
                else:
                    raise HTTPException(status_code=400, detail=f"Function not found: {function_name}")
        else:
            return {"message": "No tool calls found."}

    except HTTPException as e:
        raise  # Re-raise HTTPExceptions
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")