import subprocess
from pathlib import Path


def get_working_diff(root: str) -> dict:
    """Get unified diff of all uncommitted and staged changes."""
    root_path = Path(root)
    if not (root_path / ".git").exists():
        return {"ok": False, "error": "Not a git repository"}

    try:
        # Get staged changes
        staged = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        # Get unstaged changes
        unstaged = subprocess.run(
            ["git", "diff"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        diff_text = staged.stdout + unstaged.stdout
        return {"ok": True, "diff": diff_text}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}


def commit_agent_work(root: str, message: str) -> dict:
    """Add all changes and commit."""
    try:
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
        return {"ok": True}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"Git command failed: {e}"}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}


def revert_agent_work(root: str) -> dict:
    """Reset hard and clean."""
    try:
        subprocess.run(["git", "reset", "--hard"], cwd=root, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=root, check=True)
        return {"ok": True}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"Git command failed: {e}"}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}
