FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org

# Create directories
RUN mkdir -p /app/data
RUN mkdir -p /app/images

COPY image_db_service.py .

CMD ["python", "image_db_service.py"]