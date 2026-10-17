# Build from the repository root: docker build -f backend/Dockerfile .
FROM python:3.12-slim-bookworm AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY backend/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --require-hashes -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production LOG_LEVEL=INFO PORT=8000
RUN groupadd --gid 10001 reliability && useradd --uid 10001 --gid reliability --no-create-home reliability
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app/backend
COPY --chown=10001:10001 backend/app ./app
COPY --chown=10001:10001 backend/certs/supabase-ca.crt ./certs/supabase-ca.crt
USER 10001:10001
EXPOSE 8000
# Host is the configured exact API authority. No credential goes into the probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from app.serve import configure_platform_host; configure_platform_host(); import json,os,urllib.request; h=json.loads(os.environ['API_ALLOWED_HOSTS'])[0]; r=urllib.request.Request('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/ready',headers={'Host':h}); urllib.request.urlopen(r,timeout=4)"
CMD ["python", "-m", "app.serve"]
