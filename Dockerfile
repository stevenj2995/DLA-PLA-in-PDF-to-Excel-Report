FROM python:3.12-slim

# Tesseract is a native program, not a Python package. OCR needs the binary and
# the two language packs the reader asks for; without them a scanned DLA is
# simply skipped.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-ind \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Backend/ ./Backend/
COPY Frontend/ ./Frontend/

ENV PYTHONUNBUFFERED=1

# The host assigns the port, so it is read at start time rather than baked in.
CMD uvicorn Backend.server:app --host 0.0.0.0 --port ${PORT:-8000} --log-level warning
