import pathlib
import sys

import yaml


def load_session(name: str, config: dict) -> dict:
    """
    Load a named session from ~/.wordsmith/sessions/<name>.yaml.

    Returns dict with cookies, headers, target fields (empty dict if not found).
    """
    sessions_dir = pathlib.Path(
        config.get("sessions_dir", "~/.wordsmith/sessions/")
    ).expanduser()
    session_file = sessions_dir / f"{name}.yaml"

    if not session_file.exists():
        print(f"[warn] Session file not found: {session_file}", file=sys.stderr)
        return {}

    try:
        with session_file.open() as f:
            data = yaml.safe_load(f)
        return data or {}
    except yaml.YAMLError as exc:
        print(f"[warn] Failed to parse session file {session_file}: {exc}", file=sys.stderr)
        return {}


def save_session(name: str, data: dict, config: dict) -> None:
    """
    Save session data to ~/.wordsmith/sessions/<name>.yaml.
    Creates the sessions directory if it does not exist.
    """
    sessions_dir = pathlib.Path(
        config.get("sessions_dir", "~/.wordsmith/sessions/")
    ).expanduser()
    sessions_dir.mkdir(parents=True, exist_ok=True)

    session_file = sessions_dir / f"{name}.yaml"
    with session_file.open("w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)
    print(f"[info] Session saved: {session_file}", file=sys.stderr)
