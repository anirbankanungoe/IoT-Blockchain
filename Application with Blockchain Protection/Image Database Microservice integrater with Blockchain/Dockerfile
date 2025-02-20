FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/images \
    && mkdir -p /app/data \
    && mkdir -p /app/metrics/delay/summaries \
    && mkdir -p /app/metrics/memory/summaries \
    && mkdir -p /app/metrics/cpu/summaries \
    && mkdir -p /app/metrics/comparisons

# Copy application files
COPY image_db_service.py .
COPY blockchain_client.py .
COPY metrics_manager.py .
COPY secure_socket.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 30081

# Start the service
CMD ["python", "-u", "image_db_service.py"]