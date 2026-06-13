# Use official Python image as base
FROM python:3.11-slim

# Set work directory
WORKDIR /usr/src/app

# Install system dependencies (if needed)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY /requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source code
COPY app/ ./app/

# Set environment variables (override with .env in compose)
ENV PYTHONUNBUFFERED=1

# Expose port (FastAPI default)
EXPOSE 8000

# Default command (can be overridden in compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
