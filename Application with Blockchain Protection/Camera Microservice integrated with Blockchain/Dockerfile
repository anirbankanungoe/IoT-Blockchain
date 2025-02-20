FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    v4l-utils \
    libopencv-dev \
    python3-opencv \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    gcc \
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
    && mkdir -p /app/metrics/comparisons

# Copy application files
COPY camera_service.py .
COPY blockchain_client.py .
COPY metrics_manager.py .
COPY secure_socket.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV OPENCV_VIDEOIO_PRIORITY_MSMF=0

# Expose port
EXPOSE 5555

# Start the service
CMD ["python", "-u", "camera_service.py"]