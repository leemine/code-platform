# Context is an explicitly prepared candidate bundle, never the workspace/home.
# deps must be a clean, relocatable `uv sync --frozen --no-dev --extra native`
# environment for CPython 3.13/Linux amd64, with no editable project installed.
ARG PYTHON_IMAGE=python@sha256:227b6570d6ee07061ae6ca2eb04dedfb6d2b34045835f343065b9869e4d427ea
FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    JIUWENSWARM_CONFIG_URL=off JIUWENSWARM_DATA_DIR=/data JIUWENSWARM_CONFIG_DIR=/data/config HOME=/data/home
COPY deps /opt/venv
RUN ln -sfn /usr/local/bin/python3 /opt/venv/bin/python
COPY dist/*.whl /candidate/
COPY candidate.json /candidate/manifest.json
RUN python -c "import pathlib,json,hashlib; p=pathlib.Path('/candidate'); assert hashlib.sha256(next(p.glob('*.whl')).read_bytes()).hexdigest()==json.loads((p/'manifest.json').read_text())['wheel_sha256']"
RUN uv pip install --offline --no-cache --python /opt/venv/bin/python --no-deps /candidate/*.whl && rm -r /candidate
COPY uv.lock verify_dependencies.py candidate.json /usr/local/share/code-platform/
RUN python /usr/local/share/code-platform/verify_dependencies.py > /usr/local/share/code-platform/installed-dependencies.json
RUN groupadd --gid 1000 agentos && useradd --uid 1000 --gid 1000 --home-dir /data/home --no-create-home agentos \
    && mkdir -p /data /data/config /data/home && chown -R 1000:1000 /data
WORKDIR /data
USER 1000:1000
LABEL io.code-platform.candidate="cloud-f12-role-20261109"

FROM runtime AS account
LABEL io.code-platform.role="account-authority"
ENTRYPOINT ["python", "-m", "gateway.auth.account_http"]
CMD ["--help"]

FROM runtime AS gateway
LABEL io.code-platform.role="gateway"
ENTRYPOINT ["jiuwenswarm-gateway"]
CMD ["--host", "0.0.0.0", "--port", "19000"]

FROM runtime AS agentserver
ENV CODE_PLATFORM_ROLE=account-instance AGENT_SERVER_HOST=0.0.0.0
LABEL io.code-platform.role="agentserver"
ENTRYPOINT ["jiuwenswarm-agentserver"]
CMD ["--port", "18092"]
