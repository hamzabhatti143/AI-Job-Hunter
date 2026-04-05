FROM python:3.12-slim

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev

# Copy the rest of the source code
COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads

# Hugging Face Spaces requires port 7860
EXPOSE 7860

# Run uvicorn using the venv created by uv
CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
