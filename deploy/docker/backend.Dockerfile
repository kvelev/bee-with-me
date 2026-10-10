# Backend image for container deployments such as the develop environment (not used on field laptops).
# Build context: repository root.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# WeasyPrint (PDF export) needs Pango; same libraries the CI backend job installs
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend backend
# Persona photos for the Settings → Test mode simulation (backend/simulation.py)
COPY tools/demo-user-personas tools/demo-user-personas

# uploads/ and tiles/ are mounted from a volume in k8s; create them so the image also runs standalone
RUN useradd --uid 10001 --create-home bee \
 && mkdir -p backend/uploads tiles/bgmountains \
 && chown -R bee:bee backend/uploads tiles
USER 10001

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "20"]
