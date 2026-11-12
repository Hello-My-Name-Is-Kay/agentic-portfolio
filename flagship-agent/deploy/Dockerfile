# ARM64 image for Amazon Bedrock AgentCore Runtime (Graviton). Build context: the repository root.
#   docker build -f flagship-agent/deploy/Dockerfile .
FROM --platform=linux/arm64 python:3.12.8-slim AS builder
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY mock-booking-api ./mock-booking-api
COPY flagship-agent ./flagship-agent
RUN pip install --no-cache-dir ./mock-booking-api "./flagship-agent[agentcore]"

FROM --platform=linux/arm64 python:3.12.8-slim
RUN useradd --system --uid 1001 --create-home appuser
COPY --from=builder /opt/venv /opt/venv
COPY --chmod=755 flagship-agent/deploy/start.sh /usr/local/bin/start.sh
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    BOOKING_DB_PATH=/tmp/booking.db \
    AGENT_BOOKING_API_BASE=http://127.0.0.1:8000
USER appuser
# AgentCore routes traffic to 8080 internally and terminates TLS; never publish this port to the internet.
EXPOSE 8080
CMD ["start.sh"]
