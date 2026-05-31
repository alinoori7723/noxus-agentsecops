# Noxus AgentSecOps — minimal local/container image (Milestone 4 packaging).
# Boring on purpose: deterministic core + agent layer + Streamlit demo UI.
# No cloud CLIs, no provider SDKs, no runtime gateway.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOXUS_STREAMLIT_PORT=8501

# Non-root runtime user.
RUN useradd --create-home --uid 1000 noxus_user

WORKDIR /app

# Copy only what is needed to install and run (see .dockerignore for exclusions).
COPY pyproject.toml README.md ./
COPY src ./src

# Install the package (pulls pydantic, PyYAML, streamlit from pyproject).
RUN pip install --no-cache-dir .

# Make the working tree owned by the non-root user and drop privileges.
RUN chown -R noxus_user:noxus_user /app
USER noxus_user

EXPOSE 8501

# Default: start the local Streamlit demo UI. The port can be overridden via
# NOXUS_STREAMLIT_PORT. Shell form is used so the env var expands at runtime.
# The CLI can be run instead by overriding the command, e.g.:
#   docker run --rm noxus-agentsecops:local noxus run --mode deterministic ...
CMD streamlit run src/noxus/ui_streamlit.py --server.address=0.0.0.0 --server.port=${NOXUS_STREAMLIT_PORT:-8501}
