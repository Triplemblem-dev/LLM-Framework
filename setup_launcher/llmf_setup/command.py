from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import platform
import shutil
import subprocess
from typing import Callable, Sequence


MAX_CAPTURE_CHARS = 24_000


def command_environment() -> dict[str, str]:
    environment = os.environ.copy()
    paths = [value for value in environment.get("PATH", "").split(os.pathsep) if value]
    system = platform.system()
    if system == "Darwin":
        paths.extend(
            (
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/Applications/Docker.app/Contents/Resources/bin",
                "/Applications/Ollama.app/Contents/Resources",
            )
        )
    elif system == "Windows":
        local = environment.get("LOCALAPPDATA", "")
        program_files = environment.get("ProgramFiles", r"C:\Program Files")
        if local:
            paths.extend((str(Path(local) / "Microsoft" / "WindowsApps"), str(Path(local) / "Programs" / "Ollama")))
        paths.append(str(Path(program_files) / "Docker" / "Docker" / "resources" / "bin"))
    environment["PATH"] = os.pathsep.join(dict.fromkeys(paths))
    return environment


def find_executable(name: str) -> str | None:
    return shutil.which(name, path=command_environment().get("PATH"))


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    output: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def display_command(args: Sequence[str]) -> str:
    """Human-readable rendering only; execution never uses this string or a shell."""
    return " ".join(_quote_for_display(value) for value in args)


def _quote_for_display(value: str) -> str:
    if value and all(ch.isalnum() or ch in "-._/:=\\" for ch in value):
        return value
    return repr(value)


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    output_filter: Callable[[str], str] | None = None,
) -> CommandResult:
    """Run one fixed argument array without a shell and return bounded output."""
    safe_args = tuple(str(value) for value in args)
    if not safe_args or not safe_args[0]:
        raise ValueError("A command executable is required")
    if timeout < 1 or timeout > 3600:
        raise ValueError("Command timeout must be between 1 and 3600 seconds")

    execution_args = safe_args
    if not any(separator in safe_args[0] for separator in ("/", "\\")):
        resolved = find_executable(safe_args[0])
        if resolved:
            execution_args = (resolved, *safe_args[1:])
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            execution_args,
            cwd=str(cwd) if cwd else None,
            env=command_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
            creationflags=creationflags,
        )
        output = completed.stdout or ""
        if output_filter:
            output = output_filter(output)
        return CommandResult(
            args=safe_args,
            returncode=completed.returncode,
            output=output[-MAX_CAPTURE_CHARS:],
        )
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if output_filter:
            raw = output_filter(raw)
        return CommandResult(
            args=safe_args,
            returncode=124,
            output=raw[-MAX_CAPTURE_CHARS:],
            timed_out=True,
        )
    except OSError as exc:
        return CommandResult(safe_args, 127, f"Unable to start command: {exc}")
