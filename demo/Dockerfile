FROM python:3.11-slim

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

# Copy repository
COPY . /app

# Install package in editable mode
RUN pip install -e .

EXPOSE 8000

CMD ["python", "demo/agent.py"]
