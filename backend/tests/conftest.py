import os

# Must run before lumina_app.settings is imported anywhere, so the app's
# global engine binds to SQLite instead of the default Postgres URL.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
