# srdcheck MCP server — stdio. Built for Glama introspection and for anyone
# who wants to run the server in a container. Zero runtime dependencies; the
# SRD adapter's data (entities + atoms) is committed and ships in the package,
# so no network fetch is needed at build or run time.
FROM python:3.12-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

# A client pipes JSON-RPC 2.0 over stdin/stdout (initialize, tools/list, ...).
ENTRYPOINT ["srdcheck-mcp"]
