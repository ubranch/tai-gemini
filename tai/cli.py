import os
import sys
import signal
import platform
from types import FrameType
import subprocess
import google.generativeai as genai
from google.generativeai.types import RequestOptions
from google.api_core import retry
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from typing_extensions import TypedDict
import pathlib

# Initialize Rich console
console = Console()

# Platform detection
PLATFORM = platform.system().lower()
IS_WINDOWS = PLATFORM == "windows"
IS_LINUX = PLATFORM == "linux"
IS_MACOS = PLATFORM == "darwin"

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
                "C:\\ProgramData\\scoop\\apps\\scoop\\current"
            ]

            path_entries = env.get("PATH", "").split(os.pathsep)
            for scoop_path in scoop_paths:
                if os.path.exists(scoop_path) and scoop_path not in path_entries:
                    path_entries.append(scoop_path)

            env["PATH"] = os.pathsep.join(path_entries)

            # Properly escape and format the PowerShell command
            escaped_command = command.replace('"', '`"')
            powershell_command = f'powershell.exe -NoProfile -NonInteractive -Command "& {{{escaped_command}}}"'

            process = subprocess.Popen(
                powershell_command,
                shell=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )
        else:
            # Use the default shell on Unix-like systems
            process = subprocess.Popen(
                command,
                shell=True,
                executable="/bin/bash" if IS_LINUX else "/bin/zsh" if IS_MACOS else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )

        from threading import Thread
        from queue import Queue, Empty

        def enqueue_output(out, queue):
            for line in iter(out.readline, ''):
                queue.put(line)
            out.close()

        # Create queues for stdout and stderr
        stdout_q = Queue()
        stderr_q = Queue()

        # Start threads to read stdout and stderr
        Thread(target=enqueue_output, args=(process.stdout, stdout_q), daemon=True).start()
        Thread(target=enqueue_output, args=(process.stderr, stderr_q), daemon=True).start()

        # Read output with a timeout
        while process.poll() is None:
            try:
                # Check stdout
                try:
                    line = stdout_q.get_nowait()
                    if line:
                        console.print(line.strip())
                except Empty:
                    pass

                # Check stderr
                try:
                    line = stderr_q.get_nowait()
                    if line:
                        console.print("[red]" + line.strip() + "[/red]")
                except Empty:
                    pass
            except Exception:
                pass

        # Get remaining output
        while True:
            try:
                line = stdout_q.get_nowait()
                if line:
                    console.print(line.strip())
            except Empty:
                break

        while True:
            try:
                line = stderr_q.get_nowait()
                if line:
                    console.print("[red]" + line.strip() + "[/red]")
            except Empty:
                break

        return process.returncode
    except Exception as e:
        console.print(f"[red]Error executing command: {str(e)}[/red]")
        return 1


def handle_sigint(signum: int, frame: FrameType) -> None:
    """Signal handler for Ctrl+C (SIGINT)."""
    console.print("\nCtrl+C detected. Exiting gracefully...")
    sys.exit(0)


def get_gemini_client():
    """Configures and returns the Gemini API client with grounding enabled.

    Raises:
        ValueError: If the GEMINI_API_KEY environment variable is not set.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-exp-1206")


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
    """Returns the optimized system prompt for the LLM interaction."""
    platform_specific = "Windows Command Prompt and PowerShell" if IS_WINDOWS else "Bash and Shell commands" if IS_LINUX else "Zsh and Shell commands"

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
}}

###EXAMPLE RESPONSES###

- Example response for a KNOWN command on {PLATFORM}:
{{
    "command": "{('dir /a' if IS_WINDOWS else 'ls -la')}",
    "explanation": "Lists all files and folders, including hidden ones",
    "known_command": true,
    "platform": "{PLATFORM}"
}}

- Example response for an UNKNOWN command:
{{
    "command": "",
    "explanation": "I do not know this command",
    "known_command": false,
    "platform": "{PLATFORM}"
}}

###ADDITIONAL GUIDANCE###

- MAINTAIN clarity and conciseness in explanations.
- NEVER deviate from the JSON format.
- If a command has MULTIPLE USE CASES, provide the most common or relevant one unless otherwise specified.
- ENSURE commands are compatible with the current platform ({PLATFORM}).

###WHAT NOT TO DO###

- NEVER RETURN A RESPONSE THAT DOES NOT MATCH THE JSON SCHEMA.
- NEVER PROVIDE AN INCORRECT OR UNSUPPORTED COMMAND AS "KNOWN."
- NEVER INCLUDE UNNECESSARY INFORMATION OUTSIDE THE JSON FORMAT.
- NEVER OMIT AN EXPLANATION, EVEN FOR UNKNOWN COMMANDS.
- NEVER PROVIDE WINDOWS COMMANDS ON UNIX-LIKE SYSTEMS OR VICE VERSA.

###TASK OBJECTIVE###
ENSURE THAT ALL RESPONSES ARE PRECISE, ACCURATE, AND CONSISTENT WITH THE EXPECTED JSON SCHEMA."""


def get_response_schema() -> dict:
    """Returns the JSON schema for structured command responses."""
    return {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute"},
            "explanation": {
                "type": "string",
                "description": "Brief explanation of what the command does",
            },
            "known_command": {
                "type": "boolean",
                "description": "Whether the command is known and valid",
            },
            "platform": {
                "type": "string",
                "description": "The target platform for the command",
                "enum": ["windows", "linux", "darwin"],
            },
        },
        "required": ["command", "explanation", "known_command", "platform"],
    }


def handle_stream(response) -> str:
    """Processes the response from the LLM.

    Args:
        response: The response from the Gemini API.
    """
    if not response or not response.text:
        return ""

    # Display the response as formatted markdown
    return response.text.strip()


def send_chat_query(query: str, model) -> str:
    """Sends a query to the Gemini API.

    Args:
        query (str): The user's query.
        model: The Gemini model instance.
    """
    try:
        # Configure retry options
        retry_options = RequestOptions(
            retry=retry.Retry(
                initial=10,  # Initial delay in seconds
                multiplier=2,  # Multiplier for exponential backoff
                maximum=60,  # Maximum delay between retries
                timeout=300,  # Total timeout in seconds
            ),
        )

        # Define the response schema using TypedDict
        class CommandResponse(TypedDict):
            command: str
            explanation: str
            known_command: bool
            platform: str

        response = model.generate_content(
            [
                {"role": "user", "parts": [generate_system_prompt(), query]},
            ],
            request_options=retry_options,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=CommandResponse,
            ),
        )
        return handle_stream(response)
    except Exception as e:
        console.print(f"[red]Error generating content: {str(e)}[/red]")
        return ""


def parse_response(text: str) -> tuple[str, str]:
    """Parses the JSON response from the LLM.

    Args:
        text (str): The JSON response text.

    Returns:
        tuple[str, str]: The command and its explanation.
    """
    try:
        import json

        response_data = json.loads(text)

        if not response_data.get("known_command", False):
            console.print("[yellow]Command not recognized[/yellow]")
            return "", ""

        # Verify platform compatibility
        response_platform = response_data.get("platform", "").lower()
        if response_platform != PLATFORM:
            console.print(f"[yellow]Warning: Command is for {response_platform}, but current platform is {PLATFORM}[/yellow]")
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
    console.print(Panel(f"Current command: {command}", title="Edit Command"))
    edited_command = Prompt.ask("> ")
    return edited_command.strip() if edited_command.strip() else command


def execute_command(command: str) -> None:
    query = Prompt.ask("\nExecute the command?", choices=["y", "n", "e"], default="n")
    if query.lower() == "y":
        execute_shell_command(command)
    elif query.lower() == "e":
        edited_command = edit_command(command)
        execute_shell_command(edited_command)
    else:
        console.print("\n[yellow]Exiting...[/yellow]")


def main():
    """Initializes the Gemini client and processes the query."""
    signal.signal(signal.SIGINT, handle_sigint)

    if len(sys.argv) < 2:
        console.print("[red]Usage: tai <query>[/red]")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    try:
        model = get_gemini_client()
        response = send_chat_query(query, model)
        command, _ = parse_response(response)
        if command:
            execute_command(command)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    sys.exit(main())
