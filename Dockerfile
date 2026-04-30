FROM python:3.11-bookworm

# Expose ports
EXPOSE 80 8000

# Disable debian warnings
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /usr/src/app

# Install all dependencies in a single layer
RUN apt-get update && apt-get install -y \
    libxmlsec1-dev \
    pkg-config \
    libgdal32 \
    libgdal-dev \
    postgis \
    gdal-bin \
    python3-gdal \
    postgresql \
    postgresql-contrib \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/local/share/postgresql/extension \
    && cp /usr/share/postgresql/15/extension/postgis.control /usr/local/share/postgresql/extension \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir poetry \
    && useradd -m appuser \
    && chown -R appuser:appuser /usr/src/app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Switch to non-root user
USER appuser

# Install project dependencies
RUN poetry install --no-root

# Copy application code
COPY . .