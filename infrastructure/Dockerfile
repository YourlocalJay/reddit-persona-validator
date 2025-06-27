# Multi-stage build for Reddit Persona Validator

# Build stage
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# Final stage
FROM python:3.10-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Environment variables for Chrome
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    CHROME_BINARY_PATH=/usr/bin/chromium

# Copy wheels from builder stage
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

# Copy application code
COPY . .

# Create data directory for database
RUN mkdir -p /app/data && chmod 777 /app/data

# Create non-root user
RUN useradd -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Command to run when container starts (will be overridden in compose file)
CMD ["python", "-m", "src.interfaces.api"]
