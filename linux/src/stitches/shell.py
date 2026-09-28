"""Reading another program's output, the same way everywhere: in the C locale
(the parsers expect English — this app is used on non-English desktops) and
with nothing on stdin, so no tool can sit waiting for an answer."""

import os
import subprocess

_C = dict(os.environ, LC_ALL="C")


def output(argv: list[str], answer: str | None = None, on_line=None) -> str:
    """stdout of `argv`, each line also handed to on_line(line) as it's
    printed when that's given. Raises OSError when the tool isn't installed."""
    if on_line:
        with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                              text=True, errors="replace", env=_C) as proc:
            return _follow(proc, on_line)
    return subprocess.run(
        argv, capture_output=True, text=True, check=False, env=_C,
        input=answer, stdin=None if answer is not None else subprocess.DEVNULL,
    ).stdout


def run(argv: list[str], on_line=None) -> tuple[bool, str]:
    """For commands that change something: (succeeded, everything it printed).
    stderr goes last, so the reason for a failure is at the end — except with
    on_line, which gets both as they're printed, in the order they came."""
    try:
        if on_line:
            with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  text=True, errors="replace") as proc:
                text = _follow(proc, on_line)
            code = proc.returncode
        else:
            result = subprocess.run(argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
            text, code = result.stdout + result.stderr, result.returncode
    except OSError as exc:
        return False, str(exc)
    text = text.strip()
    return code == 0, text or ("" if code == 0 else f"exit code {code}")


def _follow(proc, on_line) -> str:
    lines = []
    for line in proc.stdout:
        lines.append(line)
        on_line(line.rstrip("\n"))
    proc.wait()
    return "".join(lines)


def tail(text: str, lines: int = 6) -> str:
    return "\n".join(text.splitlines()[-lines:])
