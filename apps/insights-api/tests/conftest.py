import os

if os.getenv("GOVCONTROL_INTEGRATION") != "1":
    os.environ.setdefault(
        "INSIGHTS_DATABASE_URL",
        "postgresql+asyncpg://govcontrol:govcontrol@127.0.0.1:5432/govcontrol",
    )
