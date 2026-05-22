from app.db import migrations


def test_loads_initial_migration() -> None:
    loaded = migrations.load_migrations()

    assert [migration.version for migration in loaded] == ["001"]
    assert loaded[0].name == "initial_auth_and_memory"
    assert len(loaded[0].checksum) == 64


def test_load_migrations_rejects_bad_file_names(tmp_path, monkeypatch) -> None:
    (tmp_path / "bad.sql").write_text("SELECT 1;", encoding="utf-8")
    monkeypatch.setattr(migrations, "MIGRATIONS_DIR", tmp_path)

    try:
        migrations.load_migrations()
    except RuntimeError as exc:
        assert "迁移文件名必须形如" in str(exc)
    else:
        raise AssertionError("bad migration name should fail")
