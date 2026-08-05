FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY aether_graph ./aether_graph

RUN pip install --no-cache-dir -e .

EXPOSE 9210

CMD ["aether-graph", "serve", "--host", "0.0.0.0", "--port", "9210", "--reload"]
