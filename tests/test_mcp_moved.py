import pytest


def test_importing_mcp_points_to_new_repo():
    with pytest.raises(ImportError, match="courtlistener-mcp"):
        import courtlistener.mcp  # noqa: F401
