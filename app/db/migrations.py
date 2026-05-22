from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from app.db.connection import connect


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_LOCK_ID = 710_003_421


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str

    @property
    def checksum(self) -> str:
        return sha256(self.sql.encode("utf-8")).hexdigest()


def run_migrations() -> None:
    migrations = load_migrations()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
            try:
                ensure_migration_table(cur)
                applied = load_applied_migrations(cur)
                for migration in migrations:
                    checksum = applied.get(migration.version)
                    if checksum == migration.checksum:
                        continue
                    if checksum is not None:
                        raise RuntimeError(
                            f"数据库迁移 {migration.version} 已执行，但文件校验和已变化"
                        )
                    apply_migration(cur, migration)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))


def load_migrations() -> list[Migration]:
    migrations = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version, _, name = path.stem.partition("_")
        if not version or not name:
            raise RuntimeError(f"迁移文件名必须形如 001_name.sql：{path.name}")
        migrations.append(
            Migration(
                version=version,
                name=name,
                path=path,
                sql=path.read_text(encoding="utf-8"),
            )
        )
    return migrations


def ensure_migration_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def load_applied_migrations(cur) -> dict[str, str]:
    cur.execute("SELECT version, checksum FROM schema_migrations")
    return {row["version"]: row["checksum"] for row in cur.fetchall()}


def apply_migration(cur, migration: Migration) -> None:
    cur.execute(migration.sql)
    cur.execute(
        """
        INSERT INTO schema_migrations (version, name, checksum)
        VALUES (%s, %s, %s)
        """,
        (migration.version, migration.name, migration.checksum),
    )
