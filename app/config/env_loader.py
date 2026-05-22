import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> None:
    env_path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line.removeprefix("export ").strip()

        key, separator, value = line.partition("=")
        if not separator:
            continue

        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = parse_env_value(value.strip())


def parse_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    return strip_inline_comment(value).strip()


def strip_inline_comment(value: str) -> str:
    in_single_quote = False
    in_double_quote = False

    for index, char in enumerate(value):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "#" and not in_single_quote and not in_double_quote:
            if index == 0 or value[index - 1].isspace():
                return value[:index]

    return value
