FROM python:3.11-slim

# Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    click \
    pydantic \
    pyyaml \
    sqlglot \
    duckdb \
    pandas \
    numpy \
    requests

# Copy repository with non-root ownership
COPY --chown=appuser:appgroup . /app

# Install package
RUN pip install -e .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 8000)); s.close()" || exit 1

CMD ["python", "demo/agent.py"]
