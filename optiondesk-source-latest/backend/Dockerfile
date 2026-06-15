# OptionDesk backend — FastAPI quant engine.
# Deployable to Render / Railway / Fly.io (anywhere that runs a Docker image).
FROM python:3.12-slim

# System deps occasionally needed by numpy/scipy/pandas wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render/Railway/Fly inject the port via $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Use shell form so $PORT is expanded at runtime.
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
