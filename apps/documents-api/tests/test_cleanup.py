from types import SimpleNamespace

import pytest

from documents_app import cleanup_e2e


@pytest.mark.asyncio
async def test_e2e_cleanup_refuses_non_development_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cleanup_e2e, "get_settings", lambda: SimpleNamespace(app_env="production")
    )

    with pytest.raises(RuntimeError, match="only in development"):
        await cleanup_e2e.cleanup()
