FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies including all OpenCV requirements
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

# Copy and install Python dependencies first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directory for logs
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Copy application code
COPY camera_service.py .

# Set environment variable for OpenCV to run headless
ENV OPENCV_VIDEOIO_PRIORITY_MSMF=0

# Run with unbuffered output
CMD ["python3", "-u", "camera_service.py"]