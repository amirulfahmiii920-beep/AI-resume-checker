# Use official Python image
FROM python:3.10-slim-bullseye

# Install wkhtmltopdf for Linux
RUN apt-get update && apt-get install -y wkhtmltopdf

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Render sets $PORT (10000 by default)
EXPOSE 10000

# Run the application
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]