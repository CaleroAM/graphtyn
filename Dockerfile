FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY graphtyn ./graphtyn
RUN pip install --no-cache-dir '.[treesitter]'
RUN useradd --create-home --uid 10001 graphtyn && mkdir -p /state /workspace && chown -R graphtyn:graphtyn /state /workspace
USER graphtyn
ENV GRAPHTYN_HOME=/state
EXPOSE 9210
ENTRYPOINT ["graphtyn"]
CMD ["serve", "--host", "0.0.0.0", "--port", "9210", "--path", "/workspace"]
