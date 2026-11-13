FROM python:3.12-slim
# Agent container: MCP client libraries and curl only. No simulator code, no admin token.
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir mcp==1.30.0
WORKDIR /workspace
