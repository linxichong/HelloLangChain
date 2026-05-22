import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config.env_loader import load_dotenv
from app.db.connection import connect
from app.db.migrations import run_migrations

load_dotenv()

SESSION_EXPIRE_HOURS = int(os.getenv("SESSION_EXPIRE_HOURS", "168"))
NORMAL_USER_MEMORY_TURN_LIMIT = int(os.getenv("NORMAL_USER_MEMORY_TURN_LIMIT", "5"))
ENABLE_PUBLIC_REGISTRATION = os.getenv("ENABLE_PUBLIC_REGISTRATION", "true").lower() == "true"
PASSWORD_ITERATIONS = 200_000


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    role: str

    @property
    def is_superuser(self) -> bool:
        return self.role == "superuser"


def init_auth_store() -> None:
    run_migrations()
    bootstrap_superuser()


def bootstrap_superuser() -> None:
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        return

    create_user(username, password, "superuser", ignore_existing=True)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
    except ValueError, TypeError:
        return False

    return secrets.compare_digest(digest, expected)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user(
    username: str,
    password: str,
    role: str = "normal",
    ignore_existing: bool = False,
) -> AuthUser:
    if role not in {"normal", "superuser"}:
        raise ValueError("用户角色只能是 normal 或 superuser")
    if not username.strip() or not password:
        raise ValueError("用户名和密码不能为空")

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_users (username, password_hash, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
                RETURNING id, username, role
                """,
                (username.strip(), hash_password(password), role),
            )
            row = cur.fetchone()
            if row is None:
                if not ignore_existing:
                    raise ValueError("用户名已存在")
                cur.execute(
                    "SELECT id, username, role FROM app_users WHERE username = %s",
                    (username.strip(),),
                )
                row = cur.fetchone()
        conn.commit()

    return AuthUser(id=row["id"], username=row["username"], role=row["role"])


def authenticate_user(username: str, password: str) -> AuthUser | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, role FROM app_users WHERE username = %s",
                (username.strip(),),
            )
            row = cur.fetchone()

    if not row or not verify_password(password, row["password_hash"]):
        return None
    return AuthUser(id=row["id"], username=row["username"], role=row["role"])


def create_session(user: AuthUser) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=SESSION_EXPIRE_HOURS)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth_sessions (token_hash, user_id, expires_at)
                VALUES (%s, %s, %s)
                """,
                (hash_token(token), user.id, expires_at),
            )
        conn.commit()
    return token, expires_at


def get_user_by_token(token: str) -> AuthUser | None:
    if not token:
        return None

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.username, u.role
                FROM auth_sessions s
                JOIN app_users u ON u.id = s.user_id
                WHERE s.token_hash = %s AND s.expires_at > now()
                """,
                (hash_token(token),),
            )
            row = cur.fetchone()

    if not row:
        return None
    return AuthUser(id=row["id"], username=row["username"], role=row["role"])


def delete_session(token: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (hash_token(token),))
        conn.commit()


def get_history(user: AuthUser, provider: str) -> list[dict[str, str]]:
    limit = None if user.is_superuser else NORMAL_USER_MEMORY_TURN_LIMIT * 2
    query = """
        SELECT role, content
        FROM conversation_messages
        WHERE user_id = %s AND provider = %s
        ORDER BY id DESC
    """
    params: tuple[object, ...]
    if limit is None:
        params = (user.id, provider)
    else:
        query += " LIMIT %s"
        params = (user.id, provider, limit)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def append_memory(user: AuthUser, provider: str, role: str, content: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_messages (user_id, provider, role, content)
                VALUES (%s, %s, %s, %s)
                """,
                (user.id, provider, role, content),
            )
        conn.commit()

    trim_memory(user, provider)


def trim_memory(user: AuthUser, provider: str) -> None:
    if user.is_superuser:
        return

    limit = NORMAL_USER_MEMORY_TURN_LIMIT * 2
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM conversation_messages
                WHERE user_id = %s
                  AND provider = %s
                  AND id NOT IN (
                    SELECT id
                    FROM conversation_messages
                    WHERE user_id = %s AND provider = %s
                    ORDER BY id DESC
                    LIMIT %s
                  )
                """,
                (user.id, provider, user.id, provider, limit),
            )
        conn.commit()


def clear_memory(user: AuthUser) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversation_messages WHERE user_id = %s", (user.id,))
        conn.commit()
