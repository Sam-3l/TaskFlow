FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy app files
COPY . .

# Copy and set up entrypoint ===
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh  # Make it executable

# Expose the port the app runs on
EXPOSE 5000

# Set the entrypoint script
ENTRYPOINT ["./entrypoint.sh"]