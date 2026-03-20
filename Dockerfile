FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip3 install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Create a non-root user and group
RUN groupadd -r django && useradd -r -g django -d /app -s /sbin/nologin django

# Copy project
COPY . /app/

# Create static files directory and set ownership
RUN mkdir -p /app/static && \
    chown -R django:django /app

# Switch to non-root user
USER django

# Collect static files
RUN python3 manage.py collectstatic --noinput
