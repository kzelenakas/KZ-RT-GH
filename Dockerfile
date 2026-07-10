# UAD 3.6 QC app - single container: FastAPI serves API + built React frontend.
# Build:  docker build -t uad36-qc .
# Run:    docker run -p 8080:8080 uad36-qc

# --- Stage 1: build the frontend ---------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: runtime ---------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app backend/app
COPY collateral_risk_engine collateral_risk_engine
COPY rules rules
COPY schemas schemas
# Only the XSDs are needed at runtime (not the multi-MB reference PDFs).
COPY ["GSE_UAD_3.6.0_v1.3_schema/Combined", "GSE_UAD_3.6.0_v1.3_schema/Combined"]
COPY --from=frontend /build/dist frontend/dist

ENV QC_DATA_DIR=/data \
    PYTHONUNBUFFERED=1
VOLUME /data

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8080"]
