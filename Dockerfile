FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[mcp]" uvicorn

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["courtlistener-mcp", "--transport", "streamable-http"]
