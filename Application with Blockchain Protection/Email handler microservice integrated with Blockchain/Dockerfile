FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/metrics/delay/summaries \
    && mkdir -p /app/metrics/memory/summaries \
    && mkdir -p /app/metrics/cpu/summaries \
    && mkdir -p /app/metrics/comparisons \
    && mkdir -p /app/temp

# Copy application files
COPY email_handler_service.py .
COPY blockchain_client.py .
COPY metrics_manager.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 30082

# Start the service
CMD ["python", "-u", "email_handler_service.py"]