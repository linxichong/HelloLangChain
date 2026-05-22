import os

from app.config.env_loader import load_dotenv, parse_env_value, strip_inline_comment


def test_parse_env_value_strips_quotes_and_inline_comments() -> None:
    assert parse_env_value('"hello # world"') == "hello # world"
    assert parse_env_value("hello # comment") == "hello"
    assert parse_env_value("hello#not-comment") == "hello#not-comment"
    assert strip_inline_comment("'# kept' # removed") == "'# kept' "


def test_load_dotenv_preserves_existing_environment(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "EXISTING=value-from-file",
                "export NEW_VALUE='hello world'",
                "COMMENTED=kept # comment",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "value-from-env")

    load_dotenv(env_file)

    assert os.environ["EXISTING"] == "value-from-env"
    assert os.environ["NEW_VALUE"] == "hello world"
    assert os.environ["COMMENTED"] == "kept"
