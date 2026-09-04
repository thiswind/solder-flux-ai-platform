FROM node:20-bookworm-slim AS fe-compute
WORKDIR /src
COPY platforms/compute/frontend/package.json platforms/compute/frontend/package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com && npm install --no-audit --no-fund
COPY platforms/compute/frontend/ ./
RUN npm run build

FROM node:20-bookworm-slim AS fe-data
WORKDIR /src
COPY platforms/data/frontend/package.json platforms/data/frontend/package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com && npm install --no-audit --no-fund
COPY platforms/data/frontend/ ./
RUN npm run build

FROM python:3.10-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
WORKDIR /app
COPY platforms/compute/requirements.txt /tmp/req-compute.txt
COPY platforms/data/backend/requirements.txt /tmp/req-data.txt
COPY deploy/docker/requirements-server.txt /tmp/req-server.txt
RUN pip install --no-cache-dir -r /tmp/req-compute.txt -r /tmp/req-data.txt -r /tmp/req-server.txt \
    && apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends libxcb1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY . /app
COPY --from=fe-compute /src/dist /app/platforms/compute/frontend/dist
COPY --from=fe-data /src/dist /app/platforms/data/frontend/dist
RUN chmod +x /app/deploy/docker/entrypoint.sh && mkdir -p /app/platforms/data/uploads /app/platforms/data/outputs
EXPOSE 8000 8001 8003
ENTRYPOINT ["/app/deploy/docker/entrypoint.sh"]
