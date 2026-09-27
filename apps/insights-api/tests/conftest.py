import os

os.environ.setdefault(
    "INSIGHTS_DATABASE_URL",
    "postgresql+asyncpg://govcontrol:govcontrol@127.0.0.1:5432/govcontrol",
)
