import httpx

_pool: httpx.AsyncBaseTransport | None = None


class SharedTransport(httpx.AsyncBaseTransport):
    """Sends through a pool that outlives the client using it."""

    def __init__(self, pool: httpx.AsyncBaseTransport) -> None:
        self.pool = pool

    async def handle_async_request(
        self, request: httpx.Request
    ) -> httpx.Response:
        return await self.pool.handle_async_request(request)

    async def aclose(self) -> None:
        """No-op: clients close their transport, the pool is closed once."""


def create_pool() -> httpx.AsyncHTTPTransport:
    """Build the connection pool."""
    return httpx.AsyncHTTPTransport(
        # Unbounded: CourtListener's rate limits own load control.
        limits=httpx.Limits(
            max_connections=None, max_keepalive_connections=20
        ),
    )


def get_transport() -> SharedTransport:
    """A transport onto the process-wide pool, created on first use."""
    global _pool
    if _pool is None:
        _pool = create_pool()
    return SharedTransport(_pool)


def set_pool(pool: httpx.AsyncBaseTransport | None) -> None:
    """Replace the process-wide pool (for tests)."""
    global _pool
    _pool = pool


async def close_pool() -> None:
    """Close the process-wide pool, if one was created."""
    global _pool
    if _pool is not None:
        pool, _pool = _pool, None
        await pool.aclose()
