FROM python:3.9-slim

# Install system dependencies for Pillow and other packages
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
RUN pip install --no-cache-dir -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org

# Create directory for temporary file storage
RUN mkdir -p /app/temp

# Copy service code
COPY email_handler_service.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose Flask port
EXPOSE 30082

# Start the service with unbuffered output
CMD ["python", "-u", "email_handler_service.py"]