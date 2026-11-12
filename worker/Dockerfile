FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 worker
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . \
 && mkdir -p /app/data && chown worker:worker /app/data

# buffer local da telemetria (montado como volume no compose)
VOLUME ["/app/data"]
USER worker

ENTRYPOINT ["pokeidle-farm"]
CMD ["run"]
