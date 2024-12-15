import os
import sys
import signal
import platform
import logging
import subprocess
import json
import requests
from typing import Optional, Tuple, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from types import FrameType
from typing_extensions import TypedDict
import pathlib

# Suppress warnings and configure logging
logging.getLogger("absl").setLevel(logging.ERROR)

# Initialize Rich console
console = Console()

# Platform detection
PLATFORM = platform.system().lower()
IS_WINDOWS = PLATFORM == "windows"
IS_LINUX = PLATFORM == "linux"
IS_MACOS = PLATFORM == "darwin"

# Gemini API configuration
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-exp-1206"


def execute_shell_command(command: str) -> int:
    """Execute a shell command in a platform-independent way.

    Args:
        command (str): The command to execute

    Returns:
        int: The return code from the command execution
    """
    try:
        if IS_WINDOWS:
            # Get the user's environment PATH
            env = os.environ.copy()

            # Add common Windows Scoop paths if not present
            scoop_paths = [
                os.path.expanduser("~/scoop/shims"),
                os.path.expanduser("~/scoop/apps/scoop/current"),
                "C:\\ProgramData\\scoop\\shims",
                "C:\\ProgramData\\scoop\\apps\\scoop\\current",
            ]

            path_entries = env.get("PATH", "").split(os.pathsep)
            for scoop_path in scoop_paths:
                if os.path.exists(scoop_path) and scoop_path not in path_entries:
                    path_entries.append(scoop_path)

            env["PATH"] = os.pathsep.join(path_entries)

            # Properly escape and format the PowerShell command
            escaped_command = command.replace('"', '`"')
            powershell_command = f'powershell.exe -NoProfile -NonInteractive -Command "& {{{escaped_command}}}"'

            # Execute command with a timeout
            try:
                result = subprocess.run(
                    powershell_command,
                    shell=True,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=30,  # 30 second timeout
                )

                # Print output
                if result.stdout:
                    console.print(result.stdout.strip())
                if result.stderr:
                    console.print("[red]" + result.stderr.strip() + "[/red]")

                return result.returncode

            except subprocess.TimeoutExpired:
                console.print("[red]Command timed out after 30 seconds[/red]")
                return 1

        else:
            # Use the default shell on Unix-like systems with timeout
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    executable=(
                        "/bin/bash" if IS_LINUX else "/bin/zsh" if IS_MACOS else None
                    ),
                    text=True,
                    capture_output=True,
                    timeout=30,  # 30 second timeout
                )

                # Print output
                if result.stdout:
                    console.print(result.stdout.strip())
                if result.stderr:
                    console.print("[red]" + result.stderr.strip() + "[/red]")

                return result.returncode

            except subprocess.TimeoutExpired:
                console.print("[red]Command timed out after 30 seconds[/red]")
                return 1

    except Exception as e:
        console.print(f"[red]Error executing command: {str(e)}[/red]")
        return 1


def handle_sigint(signum: int, frame: Optional[FrameType]) -> None:
    """Signal handler for Ctrl+C (SIGINT).

    Args:
        signum (int): The signal number
        frame (Optional[FrameType]): The current stack frame
    """
    console.print("\nCtrl+C detected. Exiting gracefully...")
    sys.exit(0)


def get_gemini_client() -> Dict[str, str]:
    """Configures and returns the Gemini API configuration.

    Returns:
        Dict[str, str]: The API configuration

    Raises:
        ValueError: If the GEMINI_API_KEY environment variable is not set
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    return {
        "api_key": api_key,
        "base_url": f"{GEMINI_API_BASE}/{GEMINI_MODEL}",
        "headers": {"Content-Type": "application/json"},
    }


def read_system_prompt() -> str:
    """Reads the system prompt from a markdown file.

    Returns:
        str: The system prompt content
    """
    prompt_path = pathlib.Path(__file__).parent / "prompt.md"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        console.print("[red]Error: prompt.md file not found[/red]")
        return generate_system_prompt()  # Fallback to the default prompt


def generate_system_prompt() -> str:
    """Returns the optimized system prompt for the LLM interaction.

    Returns:
        str: The generated system prompt
    """
    platform_specific = (
        "Windows Command Prompt and PowerShell"
        if IS_WINDOWS
        else "Bash and Shell commands" if IS_LINUX else "Zsh and Shell commands"
    )

    return f"""YOU ARE A WORLD-CLASS SYSTEM ADMINISTRATOR AND ELITE HACKER WITH UNPARALLELED EXPERTISE IN {platform_specific}. YOUR TASK IS TO ACCURATELY INTERPRET QUESTIONS ABOUT COMMANDS AND PROVIDE RESPONSES STRICTLY FOLLOWING THE SPECIFIED JSON SCHEMA.

###INSTRUCTIONS###

- ANALYZE the provided command or question with precision.
- DETERMINE the appropriate command for the current platform ({PLATFORM}).
- If the command is KNOWN, PROVIDE the exact command to execute and a BRIEF, CLEAR explanation of its function.
- If the command is UNKNOWN, EXPLICITLY INDICATE this by setting "known_command" to false and PROVIDE a generic explanation indicating the lack of knowledge.
- ENSURE your response STRICTLY MATCHES the JSON schema provided below.

###EXPECTED JSON SCHEMA###
Your response MUST conform to the following schema:
{{
    "command": "the command to execute",
    "explanation": "brief explanation of what the command does",
    "known_command": true/false,
    "platform": "{PLATFORM}"
}}"""


def get_response_schema() -> dict:
    """Returns the JSON schema for structured command responses.

    Returns:
        dict: The response schema definition
    """
    return {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "explanation": {"type": "string"},
            "known_command": {"type": "boolean"},
            "platform": {"type": "string", "enum": ["windows", "linux", "darwin"]},
        },
        "required": ["command", "explanation", "known_command", "platform"],
    }


def send_chat_query(query: str, config: Dict[str, Any]) -> str:
    """Sends a query to the Gemini API using REST.

    Args:
        query (str): The user's query
        config (Dict[str, Any]): The API configuration

    Returns:
        str: The response from the API
    """
    try:
        url = f"{config['base_url']}:generateContent?key={config['api_key']}"

        payload = {
            "contents": [
                {"parts": [{"text": generate_system_prompt()}, {"text": query}]}
            ],
            "generationConfig": {
                "temperature": 0.0,
                "response_mime_type": "application/json",
                "response_schema": get_response_schema(),
            },
        }

        response = requests.post(url, headers=config["headers"], json=payload)
        response.raise_for_status()

        data = response.json()
        if "candidates" in data and data["candidates"]:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return ""

    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error generating content: {str(e)}[/red]")
        return ""


def parse_response(text: str) -> Tuple[str, str]:
    """Parses the JSON response from the LLM.

    Args:
        text (str): The JSON response text

    Returns:
        Tuple[str, str]: A tuple containing the command and its explanation
    """
    try:
        response_data = json.loads(text)

        if not response_data.get("known_command", False):
            console.print("[yellow]Command not recognized[/yellow]")
            return "", ""

        # Verify platform compatibility
        response_platform = response_data.get("platform", "").lower()
        if response_platform != PLATFORM:
            console.print(
                f"[yellow]Warning: Command is for {response_platform}, but current platform is {PLATFORM}[/yellow]"
            )
            return "", ""

        command = response_data.get("command", "").strip()
        explanation = response_data.get("explanation", "").strip()

        if command and explanation:
            console.print(
                Panel(
                    f"Command: {command}\nExplanation: {explanation}\nPlatform: {PLATFORM}",
                    title="Command Details",
                ),
                style="bold green",
            )
            return command, explanation

        return "", ""
    except json.JSONDecodeError:
        console.print("[red]Error: Invalid response format[/red]")
        return "", ""


def edit_command(command: str) -> str:
    """Allows the user to edit a command before execution.

    Args:
        command (str): The original command

    Returns:
        str: The edited command
    """
    console.print(Panel(f"Current command: {command}", title="Edit Command"))
    edited_command = Prompt.ask("> ")
    return edited_command.strip() if edited_command.strip() else command


def execute_command(command: str) -> None:
    """Executes a command after user confirmation.

    Args:
        command (str): The command to execute
    """
    query = Prompt.ask("\nExecute the command?", choices=["y", "n", "e"], default="n")
    if query.lower() == "y":
        execute_shell_command(command)
    elif query.lower() == "e":
        edited_command = edit_command(command)
        execute_shell_command(edited_command)
    else:
        console.print("\n[yellow]Exiting...[/yellow]")


def main() -> int:
    """Main entry point for the CLI application.

    Returns:
        int: Exit code (0 for success, non-zero for errors)
    """
    try:
        signal.signal(signal.SIGINT, handle_sigint)

        if len(sys.argv) < 2:
            console.print("[red]Usage: tai <query>[/red]")
            return 1

        query = " ".join(sys.argv[1:])

        try:
            config = get_gemini_client()
            response = send_chat_query(query, config)
            command, _ = parse_response(response)
            if command:
                execute_command(command)
            return 0
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return 1
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
