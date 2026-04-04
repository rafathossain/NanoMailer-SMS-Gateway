FROM python:3.13

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies (mysqlclient needs these)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        gcc \
        libmariadb-dev \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy the application code
COPY . ./app/

COPY *.sh /app/
RUN sed -i 's/\r$//g' /app/*.sh && \
    chmod +x /app/*.sh

ENTRYPOINT ["/app/entrypoint.sh"]
