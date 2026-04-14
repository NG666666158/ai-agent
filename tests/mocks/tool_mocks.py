import time


def mock_file_read_success(path: str) -> str:
    return f"[mocked file content] loaded from {path}"


def mock_file_read_not_found(path: str) -> str:
    raise FileNotFoundError(f"File not found: {path}")


def mock_summarize_success(text: str) -> str:
    normalized = " ".join(text.split())
    return f"summary::{normalized[:120]}"


def mock_tool_timeout(*_args, **_kwargs) -> str:
    time.sleep(0.01)
    raise TimeoutError("mocked timeout")
