# tai (Terminal AI)

A minimal CLI tool that helps you remember terminal commands.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Ask for a command
tai "download youtube video as mp3"

# The tool will show the command and offer to copy it to clipboard
yt-dlp [URL] -x --audio-format mp3
Copy to clipboard? [y/n]
```

## Requirements

- Python 3.x
- GEMINI_API_KEY environment variable

## Setup

```bash
# Set your Gemini API key
export GEMINI_API_KEY="your_api_key_here"
```
