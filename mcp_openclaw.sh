#!/usr/bin/env bash
# Wrapper para lanzar el MCP de AetherGraph dentro del contenedor openclaw-agent.
# Rutas del contenedor: /home/node/proyectos = bind de /mnt/share-code (VM) = Documentos del host.
# El daemon HTTP de AetherGraph vive en el HOST; desde el contenedor se alcanza
# por la IP gateway de la VM (192.168.122.1), no por 127.0.0.1.
export PYTHONPATH="/home/node/proyectos/docker/PROYECTOS/aether-graph${PYTHONPATH:+:$PYTHONPATH}"
export AETHER_DAEMON_URL="${AETHER_DAEMON_URL:-http://192.168.122.1:9210}"
exec python3 -m aether_graph.cli mcp --path /home/node/proyectos/docker/PROYECTOS/recodding/366metrics-cdk
