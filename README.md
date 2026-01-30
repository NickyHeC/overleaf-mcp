# Overleaf MCP Server

An Overleaf MCP server built with the [Dedalus MCP framework](https://dedaluslabs.ai). Provides seamless integration with Overleaf projects via git, enabling local LaTeX editing with automatic synchronization to Overleaf cloud.

## Features

### Available Tools

#### File Operations

| Tool | Description |
|------|-------------|
| `read_text` | Search for and read a specific matched section from a file (by pattern or line numbers) |
| `write_text` | Replace a designated section in a file with new text (by pattern or line numbers) |
| `edit_latex_selection` | Edit a specific selection of text in a LaTeX file according to LaTeX rules |
| `edit_latex_file` | Edit or create a complete LaTeX file with new content |

#### Overleaf Git Integration

| Tool | Description |
|------|-------------|
| `pull_overleaf_project` | Pull a designated project from Overleaf using project URL and save to local directory |
| `push_to_overleaf` | Push local changes to Overleaf project automatically |
| `check_sync_status` | Check for unsynchronized changes between Overleaf cloud and local project |

### Key Features

- **Automatic Sync Checking**: All edit operations check sync status before proceeding, preventing conflicts
- **Automatic Push**: Edit operations automatically push changes to Overleaf after successful edits
- **URL Conversion**: Automatically converts Overleaf project URLs (`https://www.overleaf.com/project/...`) to git URLs
- **Sync Warnings**: Detects and warns about:
  - Edits on Overleaf cloud (suggests pull)
  - Local edits not pushed (suggests push)
  - Uncommitted local changes

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip
- Overleaf git token (get from [Overleaf Git Integration](https://docs.overleaf.com/integrations-and-add-ons/git-integration-and-github-synchronization/git-integration))
- Dedalus API Key

## Setup

1. **Clone the repository**

```bash
git clone https://github.com/NickyHeC/overleaf-mcp.git
cd overleaf-mcp
```

2. **Install dependencies**

Using uv (recommended):
```bash
uv sync
```

Or using pip:
```bash
pip install -e .
```

3. **Configure environment variables**

Create a `.env` file in the project root:

```env
OVERLEAF_GIT_TOKEN=olp_your_token_here
OVERLEAF_PROJECT_URL=https://www.overleaf.com/project/your_project_id
DEDALUS_API_KEY=your_dedalus_api_key
DEDALUS_AS_URL=https://as.dedaluslabs.ai
```

## Usage

### Running the Server

```bash
python src/main.py
```

Or using uv:
```bash
uv run python src/main.py
```

The server will start on `http://127.0.0.1:8080/mcp`

### Client Usage

```python
import asyncio
import os

from dotenv import load_dotenv
from dedalus_labs import AsyncDedalus, DedalusRunner

load_dotenv()

async def main():
    client = AsyncDedalus(
        api_key=os.getenv("DEDALUS_API_KEY"),
        base_url=os.getenv("DEDALUS_API_URL"),
        as_base_url=os.getenv("DEDALUS_AS_URL"),
    )
    runner = DedalusRunner(client)

    result = await runner.run(
        input="Read the first paragraph from the Overleaf project and edit it",
        model="openai/gpt-4",
        mcp_servers=["your-username/overleaf-mcp"],
    )

    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
```

## Tool Examples

### Pull an Overleaf Project

```python
# Pulls project to ~/Desktop/overleaf-{project_id} by default
pull_overleaf_project(
    project_url="https://www.overleaf.com/project/6887eac2749d275ab052a76e"
)
```

### Read Text from File

```python
# Read by line numbers
read_text(
    file_path="/path/to/file.tex",
    start_line=1,
    end_line=10
)

# Read by pattern
read_text(
    file_path="/path/to/file.tex",
    pattern="My journey",
    use_regex=False
)
```

### Edit LaTeX File

```python
# Edit a selection
edit_latex_selection(
    file_path="/path/to/file.tex",
    start_line=5,
    end_line=7,
    new_content="New LaTeX content here"
)

# Edit entire file
edit_latex_file(
    file_path="/path/to/file.tex",
    content="\\documentclass{article}\n\\begin{document}\n..."
)
```

### Check Sync Status

```python
check_sync_status(repo_path="/path/to/project")
# Returns warnings and suggestions if not synced
```

## How It Works

1. **Project URL Conversion**: The server automatically converts Overleaf project URLs to git URLs:
   - `https://www.overleaf.com/project/1234567` → `https://git.overleaf.com/1234567`

2. **Authentication**: Uses Overleaf git token in the format:
   - `https://git:{token}@git.overleaf.com/{project_id}`

3. **Sync Protection**: Before any edit operation:
   - Checks if local is behind remote (suggests pull)
   - Checks if local has unpushed commits (suggests push)
   - Checks for uncommitted changes (suggests commit)

4. **Automatic Push**: After successful edits, changes are automatically:
   - Committed with descriptive messages
   - Pushed to Overleaf cloud

## Project Structure

```
overleaf-mcp/
├── src/
│   ├── __init__.py      # Package initialization
│   ├── main.py          # Entry point
│   ├── server.py        # Server setup and configuration
│   └── tools.py         # Tool definitions
├── pyproject.toml       # Project configuration and dependencies
├── README.md
├── LICENSE
└── PROJECT.md           # Project notes and requirements
```

## Configuration

### Environment Variables

- `OVERLEAF_GIT_TOKEN`: Your Overleaf git authentication token
- `OVERLEAF_PROJECT_URL`: Default Overleaf project URL (optional)
- `DEDALUS_API_KEY`: Your Dedalus API key
- `DEDALUS_AS_URL`: Dedalus authorization server URL (default: https://as.dedaluslabs.ai)

## License

MIT License - see [LICENSE](LICENSE) for details.
