from dedalus_mcp import tool
from pydantic import BaseModel
import subprocess
import os
import re
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    try:
        load_dotenv()
    except (PermissionError, FileNotFoundError):
        pass  # .env file not accessible, will use defaults
except ImportError:
    pass  # python-dotenv not installed, will use defaults


# --- Result Models ---

class ToolResult(BaseModel):
    success: bool
    message: str
    data: dict = {}


class PullResult(BaseModel):
    success: bool
    message: str
    local_path: str = ""
    files_pulled: list[str] = []


class SyncStatusResult(BaseModel):
    success: bool
    message: str
    is_synced: bool = False
    local_ahead: bool = False
    remote_ahead: bool = False
    has_uncommitted: bool = False
    warnings: list[str] = []
    suggestions: list[str] = []
    local_commits_ahead: int = 0
    remote_commits_ahead: int = 0


class ReadTextResult(BaseModel):
    success: bool
    message: str
    text: str = ""
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    match_info: dict = {}


# --- Helper Functions ---

def find_git_repo_root(file_path: str) -> Optional[str]:
    """Find the git repository root directory from a file path."""
    path = Path(file_path).resolve()
    
    # If it's a directory, start there; otherwise use parent
    if path.is_dir():
        current = path
    else:
        current = path.parent
    
    # Walk up the directory tree to find .git
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent
    
    return None


# --- Tools ---

@tool(description="Search for and read a specific matched section from a file")
def read_text(file_path: str, pattern: Optional[str] = None, start_line: Optional[int] = None, end_line: Optional[int] = None, use_regex: bool = False) -> ReadTextResult:
    """
    Search for and read a specific matched section from a file.
    Can search by pattern (regex or exact match) or by line numbers.
    
    Args:
        file_path: Path to the file to read from
        pattern: Text pattern to search for (if None, uses line numbers)
        start_line: Starting line number (1-indexed, required if pattern is None)
        end_line: Ending line number (1-indexed, inclusive, required if pattern is None)
        use_regex: Whether to treat pattern as regex (default: False, exact match)
    
    Returns:
        ReadTextResult with the matched text and location information
    """
    try:
        file = Path(file_path)
        if not file.exists():
            return ReadTextResult(
                success=False,
                message=f"File not found: {file_path}",
            )
        
        content = file.read_text(encoding="utf-8")
        lines = content.splitlines()
        
        # Search by pattern
        if pattern is not None:
            if use_regex:
                # Regex search
                match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
                if match:
                    matched_text = match.group(0)
                    # Find line numbers
                    start_pos = match.start()
                    end_pos = match.end()
                    start_line_num = content[:start_pos].count('\n') + 1
                    end_line_num = content[:end_pos].count('\n') + 1
                    
                    return ReadTextResult(
                        success=True,
                        message=f"Found pattern match in {file_path}",
                        text=matched_text,
                        start_line=start_line_num,
                        end_line=end_line_num,
                        match_info={
                            "pattern": pattern,
                            "match_start": match.start(),
                            "match_end": match.end(),
                        },
                    )
                else:
                    return ReadTextResult(
                        success=False,
                        message=f"Pattern not found in {file_path}",
                    )
            else:
                # Exact text search
                if pattern in content:
                    start_pos = content.find(pattern)
                    end_pos = start_pos + len(pattern)
                    matched_text = pattern
                    start_line_num = content[:start_pos].count('\n') + 1
                    end_line_num = content[:end_pos].count('\n') + 1
                    
                    return ReadTextResult(
                        success=True,
                        message=f"Found text match in {file_path}",
                        text=matched_text,
                        start_line=start_line_num,
                        end_line=end_line_num,
                        match_info={
                            "pattern": pattern,
                            "match_start": start_pos,
                            "match_end": end_pos,
                        },
                    )
                else:
                    return ReadTextResult(
                        success=False,
                        message=f"Text not found in {file_path}",
                    )
        
        # Search by line numbers
        elif start_line is not None and end_line is not None:
            # Validate line numbers
            if start_line < 1 or end_line > len(lines) or start_line > end_line:
                return ReadTextResult(
                    success=False,
                    message=f"Invalid line range: {start_line}-{end_line} (file has {len(lines)} lines)",
                )
            
            # Extract lines (convert to 0-indexed)
            selected_lines = lines[start_line - 1:end_line]
            matched_text = "\n".join(selected_lines)
            
            return ReadTextResult(
                success=True,
                message=f"Read lines {start_line}-{end_line} from {file_path}",
                text=matched_text,
                start_line=start_line,
                end_line=end_line,
                match_info={
                    "total_lines": len(lines),
                },
            )
        else:
            return ReadTextResult(
                success=False,
                message="Either pattern or both start_line and end_line must be provided",
            )
    except Exception as e:
        return ReadTextResult(
            success=False,
            message=f"Error reading text: {str(e)}",
        )


@tool(description="Replace a designated section in a file with new text")
def write_text(file_path: str, new_content: str, pattern: Optional[str] = None, start_line: Optional[int] = None, end_line: Optional[int] = None, use_regex: bool = False) -> ToolResult:
    """
    Replace a designated section in a file with new text.
    Can replace by pattern match (regex or exact) or by line numbers.
    
    Args:
        file_path: Path to the file to edit
        new_content: The new content to replace the section with
        pattern: Text pattern to search for and replace (if None, uses line numbers)
        start_line: Starting line number (1-indexed, required if pattern is None)
        end_line: Ending line number (1-indexed, inclusive, required if pattern is None)
        use_regex: Whether to treat pattern as regex (default: False, exact match)
    
    Returns:
        ToolResult with success status and message
    """
    try:
        # Check sync status before editing
        repo_root = find_git_repo_root(file_path)
        if repo_root:
            sync_status = check_sync_status(repo_root)
            if sync_status.success and sync_status.warnings:
                # Pause edits if there are warnings
                warning_msg = "⚠️ Sync check failed. Please resolve sync issues before editing:\n\n"
                for warning in sync_status.warnings:
                    warning_msg += f"  • {warning}\n"
                warning_msg += "\nSuggestions:\n"
                for suggestion in sync_status.suggestions:
                    warning_msg += f"  • {suggestion}\n"
                warning_msg += "\nAfter resolving sync issues, you can retry the edit operation."
                
                return ToolResult(
                    success=False,
                    message=warning_msg,
                    data={
                        "sync_status": {
                            "is_synced": sync_status.is_synced,
                            "local_ahead": sync_status.local_ahead,
                            "remote_ahead": sync_status.remote_ahead,
                            "has_uncommitted": sync_status.has_uncommitted,
                            "warnings": sync_status.warnings,
                            "suggestions": sync_status.suggestions,
                        }
                    },
                )
        
        file = Path(file_path)
        if not file.exists():
            return ToolResult(
                success=False,
                message=f"File not found: {file_path}",
            )
        
        content = file.read_text(encoding="utf-8")
        lines = content.splitlines()
        
        # Replace by pattern
        if pattern is not None:
            if use_regex:
                # Regex replacement
                if re.search(pattern, content, re.MULTILINE | re.DOTALL):
                    new_content_full = re.sub(pattern, new_content, content, flags=re.MULTILINE | re.DOTALL)
                    file.write_text(new_content_full, encoding="utf-8")
                    
                    # Push to Overleaf
                    repo_root = find_git_repo_root(file_path)
                    push_message = f"Updated {file_path} via write_text (regex)"
                    if repo_root:
                        push_result = push_to_overleaf(repo_root, push_message)
                        if not push_result.success and "nothing to commit" not in push_result.message.lower():
                            return ToolResult(
                                success=True,
                                message=f"Successfully replaced regex pattern in {file_path}, but push failed: {push_result.message}",
                                data={
                                    "file_path": file_path,
                                    "pattern": pattern,
                                    "replacement_length": len(new_content),
                                    "push_status": push_result.message,
                                },
                            )
                    
                    return ToolResult(
                        success=True,
                        message=f"Successfully replaced regex pattern in {file_path}",
                        data={
                            "file_path": file_path,
                            "pattern": pattern,
                            "replacement_length": len(new_content),
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        message=f"Pattern not found in {file_path}",
                    )
            else:
                # Exact text replacement
                if pattern in content:
                    new_content_full = content.replace(pattern, new_content, 1)  # Replace first occurrence
                    file.write_text(new_content_full, encoding="utf-8")
                    
                    # Push to Overleaf
                    repo_root = find_git_repo_root(file_path)
                    push_message = f"Updated {file_path} via write_text (exact match)"
                    if repo_root:
                        push_result = push_to_overleaf(repo_root, push_message)
                        if not push_result.success and "nothing to commit" not in push_result.message.lower():
                            return ToolResult(
                                success=True,
                                message=f"Successfully replaced text in {file_path}, but push failed: {push_result.message}",
                                data={
                                    "file_path": file_path,
                                    "pattern": pattern,
                                    "replacement_length": len(new_content),
                                    "push_status": push_result.message,
                                },
                            )
                    
                    return ToolResult(
                        success=True,
                        message=f"Successfully replaced text in {file_path}",
                        data={
                            "file_path": file_path,
                            "pattern": pattern,
                            "replacement_length": len(new_content),
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        message=f"Text not found in {file_path}",
                    )
        
        # Replace by line numbers
        elif start_line is not None and end_line is not None:
            # Validate line numbers
            if start_line < 1 or end_line > len(lines) or start_line > end_line:
                return ToolResult(
                    success=False,
                    message=f"Invalid line range: {start_line}-{end_line} (file has {len(lines)} lines)",
                )
            
            # Replace the selection (convert to 0-indexed)
            new_lines = lines[:start_line - 1] + new_content.splitlines() + lines[end_line:]
            file.write_text("\n".join(new_lines), encoding="utf-8")
            
            # Push to Overleaf
            repo_root = find_git_repo_root(file_path)
            push_message = f"Updated {file_path} via write_text"
            if repo_root:
                push_result = push_to_overleaf(repo_root, push_message)
                if not push_result.success and "nothing to commit" not in push_result.message.lower():
                    # If push failed (but not because nothing to commit), include in message
                    return ToolResult(
                        success=True,
                        message=f"Successfully replaced lines {start_line}-{end_line} in {file_path}, but push failed: {push_result.message}",
                        data={
                            "file_path": file_path,
                            "lines_replaced": end_line - start_line + 1,
                            "new_lines": len(new_content.splitlines()),
                            "push_status": push_result.message,
                        },
                    )
            
            return ToolResult(
                success=True,
                message=f"Successfully replaced lines {start_line}-{end_line} in {file_path}",
                data={
                    "file_path": file_path,
                    "lines_replaced": end_line - start_line + 1,
                    "new_lines": len(new_content.splitlines()),
                },
            )
        else:
            return ToolResult(
                success=False,
                message="Either pattern or both start_line and end_line must be provided",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Error writing text: {str(e)}",
        )


@tool(description="Edit a selection of text in a LaTeX file according to LaTeX rules")
def edit_latex_selection(file_path: str, start_line: int, end_line: int, new_content: str) -> ToolResult:
    """
    Edit a specific selection of text in a LaTeX file, replacing lines from start_line to end_line with new_content.
    The new_content should follow LaTeX rules and formatting.
    This function uses read_text and write_text internally.
    
    Args:
        file_path: Path to the LaTeX file to edit
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed, inclusive)
        new_content: The new LaTeX content to replace the selection with
    
    Returns:
        ToolResult with success status and message
    """
    # Check sync status before editing
    repo_root = find_git_repo_root(file_path)
    if repo_root:
        sync_status = check_sync_status(repo_root)
        if sync_status.success and sync_status.warnings:
            # Pause edits if there are warnings
            warning_msg = "⚠️ Sync check failed. Please resolve sync issues before editing:\n\n"
            for warning in sync_status.warnings:
                warning_msg += f"  • {warning}\n"
            warning_msg += "\nSuggestions:\n"
            for suggestion in sync_status.suggestions:
                warning_msg += f"  • {suggestion}\n"
            warning_msg += "\nAfter resolving sync issues, you can retry the edit operation."
            
            return ToolResult(
                success=False,
                message=warning_msg,
                data={
                    "sync_status": {
                        "is_synced": sync_status.is_synced,
                        "local_ahead": sync_status.local_ahead,
                        "remote_ahead": sync_status.remote_ahead,
                        "has_uncommitted": sync_status.has_uncommitted,
                        "warnings": sync_status.warnings,
                        "suggestions": sync_status.suggestions,
                    }
                },
            )
    
    # First, read the current selection to verify it exists
    read_result = read_text(file_path, start_line=start_line, end_line=end_line)
    
    if not read_result.success:
        return ToolResult(
            success=False,
            message=f"Failed to read selection: {read_result.message}",
        )
    
    # Then, write the new content to replace the selection
    write_result = write_text(file_path, new_content, start_line=start_line, end_line=end_line)
    
    if not write_result.success:
        return ToolResult(
            success=False,
            message=f"Failed to write selection: {write_result.message}",
        )
    
    # Push to Overleaf
    repo_root = find_git_repo_root(file_path)
    push_message = f"Updated {file_path} via edit_latex_selection"
    push_success = True
    push_status = ""
    if repo_root:
        push_result = push_to_overleaf(repo_root, push_message)
        push_success = push_result.success or "nothing to commit" in push_result.message.lower()
        push_status = push_result.message
    
    # Return success with combined information
    message = f"Successfully edited lines {start_line}-{end_line} in {file_path}"
    if not push_success:
        message += f", but push failed: {push_status}"
    
    return ToolResult(
        success=True,
        message=message,
        data={
            "file_path": file_path,
            "lines_edited": end_line - start_line + 1,
            "new_lines": len(new_content.splitlines()),
            "old_text_length": len(read_result.text),
            "new_text_length": len(new_content),
            "push_status": push_status,
        },
    )


@tool(description="Push local changes to Overleaf project automatically")
def push_to_overleaf(repo_path: str = ".", commit_message: str = "Update from MCP server") -> ToolResult:
    """
    Commit and push local changes to the Overleaf git repository.
    
    Args:
        repo_path: Path to the git repository (default: current directory)
        commit_message: Git commit message for the changes
    
    Returns:
        ToolResult with push status and output
    """
    try:
        repo = Path(repo_path)
        if not (repo / ".git").exists():
            return ToolResult(
                success=False,
                message=f"Not a git repository: {repo_path}",
            )
        
        # Add all changes
        add_result = subprocess.run(
            ["git", "-C", str(repo), "add", "-A"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if add_result.returncode != 0:
            return ToolResult(
                success=False,
                message=f"Failed to stage changes: {add_result.stderr}",
            )
        
        # Commit changes
        commit_result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", commit_message],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Check if there were changes to commit
        if "nothing to commit" in commit_result.stdout.lower():
            return ToolResult(
                success=True,
                message="No changes to commit",
                data={"output": commit_result.stdout},
            )
        
        # Push to remote
        push_result = subprocess.run(
            ["git", "-C", str(repo), "push", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if push_result.returncode == 0:
            return ToolResult(
                success=True,
                message="Successfully pushed changes to Overleaf",
                data={"output": push_result.stdout},
            )
        else:
            # Try 'master' branch if 'main' fails
            push_result_master = subprocess.run(
                ["git", "-C", str(repo), "push", "origin", "master"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if push_result_master.returncode == 0:
                return ToolResult(
                    success=True,
                    message="Successfully pushed changes to Overleaf (master branch)",
                    data={"output": push_result_master.stdout},
                )
            else:
                return ToolResult(
                    success=False,
                    message=f"Failed to push to Overleaf: {push_result_master.stderr}",
                    data={"output": push_result_master.stdout},
                )
    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            message="Git operation timed out",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Error pushing to Overleaf: {str(e)}",
        )


@tool(description="Edit a LaTeX project file with new content following LaTeX rules")
def edit_latex_file(file_path: str, content: str) -> ToolResult:
    """
    Edit or create a LaTeX file with the provided content.
    The content should follow LaTeX rules and formatting.
    
    Args:
        file_path: Path to the LaTeX file (will be created if it doesn't exist)
        content: The complete LaTeX content for the file
    
    Returns:
        ToolResult with success status and message
    """
    try:
        # Check sync status before editing (only if file exists and is in a git repo)
        file = Path(file_path)
        if file.exists():
            repo_root = find_git_repo_root(file_path)
            if repo_root:
                sync_status = check_sync_status(repo_root)
                if sync_status.success and sync_status.warnings:
                    # Pause edits if there are warnings
                    warning_msg = "⚠️ Sync check failed. Please resolve sync issues before editing:\n\n"
                    for warning in sync_status.warnings:
                        warning_msg += f"  • {warning}\n"
                    warning_msg += "\nSuggestions:\n"
                    for suggestion in sync_status.suggestions:
                        warning_msg += f"  • {suggestion}\n"
                    warning_msg += "\nAfter resolving sync issues, you can retry the edit operation."
                    
                    return ToolResult(
                        success=False,
                        message=warning_msg,
                        data={
                            "sync_status": {
                                "is_synced": sync_status.is_synced,
                                "local_ahead": sync_status.local_ahead,
                                "remote_ahead": sync_status.remote_ahead,
                                "has_uncommitted": sync_status.has_uncommitted,
                                "warnings": sync_status.warnings,
                                "suggestions": sync_status.suggestions,
                            }
                        },
                    )
        
        file.parent.mkdir(parents=True, exist_ok=True)
        
        file.write_text(content, encoding="utf-8")
        
        # Push to Overleaf
        repo_root = find_git_repo_root(file_path)
        push_message = f"Updated {file_path} via edit_latex_file"
        push_success = True
        push_status = ""
        if repo_root:
            push_result = push_to_overleaf(repo_root, push_message)
            push_success = push_result.success or "nothing to commit" in push_result.message.lower()
            push_status = push_result.message
        
        message = f"Successfully edited {file_path}"
        if not push_success:
            message += f", but push failed: {push_status}"
        
        return ToolResult(
            success=True,
            message=message,
            data={
                "file_path": file_path,
                "bytes_written": len(content.encode("utf-8")),
                "lines": len(content.splitlines()),
                "push_status": push_status,
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Error editing LaTeX file: {str(e)}",
        )


def convert_overleaf_url_to_git(overleaf_url: str) -> str:
    """
    Convert an Overleaf project URL to a git URL.
    
    Examples:
        https://www.overleaf.com/project/1234567 -> https://git.overleaf.com/1234567
        https://git.overleaf.com/1234567 -> https://git.overleaf.com/1234567 (already git URL)
    """
    # If already a git URL, return as is
    if "git.overleaf.com" in overleaf_url:
        return overleaf_url
    
    # Extract project ID from Overleaf project URL
    # Format: https://www.overleaf.com/project/PROJECT_ID
    match = re.search(r'/project/([a-zA-Z0-9]+)', overleaf_url)
    if match:
        project_id = match.group(1)
        return f"https://git.overleaf.com/{project_id}"
    
    # Try to extract project ID from other formats
    parts = overleaf_url.rstrip('/').split('/')
    if parts:
        project_id = parts[-1]
        return f"https://git.overleaf.com/{project_id}"
    
    raise ValueError(f"Could not extract project ID from URL: {overleaf_url}")


@tool(description="Pull a designated project from Overleaf using project URL and save to local directory")
def pull_overleaf_project(project_url: Optional[str] = None, local_path: Optional[str] = None, token: Optional[str] = None) -> PullResult:
    """
    Clone or pull an Overleaf project from the provided URL to a local directory.
    Accepts both Overleaf project URLs (https://www.overleaf.com/project/...) and git URLs (https://git.overleaf.com/...).
    If project_url or token are not provided, they will be loaded from .env file or environment variables.
    
    Args:
        project_url: Overleaf project URL (e.g., https://www.overleaf.com/project/1234567) or git URL (e.g., https://git.overleaf.com/1234567)
        local_path: Local directory path where the project should be cloned/pulled (default: Desktop)
        token: Overleaf git token (default: from OVERLEAF_GIT_TOKEN env var or PROJECT.md)
    
    Returns:
        PullResult with success status, local path, and list of files pulled
    """
    try:
        # Load from environment if not provided
        if not token:
            token = os.getenv("OVERLEAF_GIT_TOKEN", "olp_3qbcfOFz3NXQfCrIqdjRCNG6Rj4JJJ2csSuD")
        
        if not project_url:
            project_url = os.getenv("OVERLEAF_PROJECT_URL")
            if not project_url:
                return PullResult(
                    success=False,
                    message="No project URL provided and OVERLEAF_PROJECT_URL not found in environment",
                )
        
        # Convert Overleaf project URL to git URL if needed
        git_url = convert_overleaf_url_to_git(project_url)
        
        # Determine local path
        if not local_path:
            desktop = Path.home() / "Desktop"
            # Extract project ID for folder name
            project_id = git_url.split('/')[-1]
            local_path = str(desktop / f"overleaf-{project_id}")
        
        local_dir = Path(local_path)
        
        # Construct authenticated URL
        # Format: https://git:<token>@git.overleaf.com/[project-id]
        # Overleaf requires 'git' as username and token as password
        authenticated_url = git_url.replace("https://", f"https://git:{token}@")
        
        # Check if directory exists and has .git (already cloned)
        if (local_dir / ".git").exists():
            # Pull latest changes
            pull_result = subprocess.run(
                ["git", "-C", str(local_dir), "pull", "origin", "main"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if pull_result.returncode != 0:
                # Try master branch
                pull_result = subprocess.run(
                    ["git", "-C", str(local_dir), "pull", "origin", "master"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            
            if pull_result.returncode == 0:
                files = [str(f.relative_to(local_dir)) for f in local_dir.rglob("*") if f.is_file() and ".git" not in str(f)]
                return PullResult(
                    success=True,
                    message=f"Successfully pulled latest changes to {local_path}",
                    local_path=str(local_dir.absolute()),
                    files_pulled=files[:50],  # Limit to first 50 files
                )
            else:
                return PullResult(
                    success=False,
                    message=f"Failed to pull changes: {pull_result.stderr}",
                )
        else:
            # Clone the repository
            local_dir.parent.mkdir(parents=True, exist_ok=True)
            
            clone_result = subprocess.run(
                ["git", "clone", authenticated_url, str(local_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if clone_result.returncode == 0:
                files = [str(f.relative_to(local_dir)) for f in local_dir.rglob("*") if f.is_file() and ".git" not in str(f)]
                return PullResult(
                    success=True,
                    message=f"Successfully cloned Overleaf project to {local_path}",
                    local_path=str(local_dir.absolute()),
                    files_pulled=files[:50],  # Limit to first 50 files
                )
            else:
                return PullResult(
                    success=False,
                    message=f"Failed to clone project: {clone_result.stderr}",
                )
    except subprocess.TimeoutExpired:
        return PullResult(
            success=False,
            message="Git operation timed out",
        )
    except Exception as e:
        return PullResult(
            success=False,
            message=f"Error pulling Overleaf project: {str(e)}",
        )


@tool(description="Check for unsynchronized changes between Overleaf cloud and local project")
def check_sync_status(repo_path: str = ".") -> SyncStatusResult:
    """
    Check if the local project is synchronized with Overleaf cloud.
    Detects if there are edits on Overleaf cloud (suggests pull) or local edits (suggests push).
    
    Args:
        repo_path: Path to the git repository (default: current directory)
    
    Returns:
        SyncStatusResult with sync status, warnings, and suggestions
    """
    try:
        repo = Path(repo_path)
        if not (repo / ".git").exists():
            return SyncStatusResult(
                success=False,
                message=f"Not a git repository: {repo_path}",
            )
        
        warnings = []
        suggestions = []
        
        # Check for uncommitted local changes
        status_result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        has_uncommitted = bool(status_result.stdout.strip())
        
        if has_uncommitted:
            warnings.append("You have uncommitted local changes")
            suggestions.append("Commit your changes before syncing")
        
        # Fetch latest from remote to check for updates
        fetch_result = subprocess.run(
            ["git", "-C", str(repo), "fetch", "origin"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Check if local is behind remote (edits on Overleaf cloud)
        behind_result = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", "HEAD..origin/master"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Check if local is ahead of remote (local edits not pushed)
        ahead_result = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", "origin/master..HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Try master branch if main doesn't work
        if behind_result.returncode != 0:
            behind_result = subprocess.run(
                ["git", "-C", str(repo), "rev-list", "--count", "HEAD..origin/master"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        if ahead_result.returncode != 0:
            ahead_result = subprocess.run(
                ["git", "-C", str(repo), "rev-list", "--count", "origin/master..HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        
        remote_ahead = False
        local_ahead = False
        remote_commits_ahead = 0
        local_commits_ahead = 0
        
        if behind_result.returncode == 0:
            try:
                remote_commits_ahead = int(behind_result.stdout.strip())
                remote_ahead = remote_commits_ahead > 0
            except ValueError:
                pass
        
        if ahead_result.returncode == 0:
            try:
                local_commits_ahead = int(ahead_result.stdout.strip())
                local_ahead = local_commits_ahead > 0
            except ValueError:
                pass
        
        # Generate warnings and suggestions
        if remote_ahead:
            warnings.append(f"Overleaf cloud has {remote_commits_ahead} commit(s) that are not in your local project")
            suggestions.append("Run pull_overleaf_project to sync changes from Overleaf cloud")
        
        if local_ahead:
            warnings.append(f"Your local project has {local_commits_ahead} commit(s) that are not on Overleaf cloud")
            suggestions.append("Run push_to_overleaf to sync your local changes to Overleaf cloud")
        
        is_synced = not remote_ahead and not local_ahead and not has_uncommitted
        
        if is_synced:
            message = "Project is fully synchronized with Overleaf cloud"
        else:
            message = f"Project has unsynchronized changes: {len(warnings)} issue(s) found"
        
        return SyncStatusResult(
            success=True,
            message=message,
            is_synced=is_synced,
            local_ahead=local_ahead,
            remote_ahead=remote_ahead,
            has_uncommitted=has_uncommitted,
            warnings=warnings,
            suggestions=suggestions,
            local_commits_ahead=local_commits_ahead,
            remote_commits_ahead=remote_commits_ahead,
        )
    except subprocess.TimeoutExpired:
        return SyncStatusResult(
            success=False,
            message="Git operation timed out",
        )
    except Exception as e:
        return SyncStatusResult(
            success=False,
            message=f"Error checking sync status: {str(e)}",
        )


tools = [
    read_text,
    write_text,
    edit_latex_selection,
    push_to_overleaf,
    edit_latex_file,
    pull_overleaf_project,
    check_sync_status,
]
