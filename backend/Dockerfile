FROM python:3.11-slim

# System deps: libglib for PyMuPDF; remove poppler/libmagic (no longer needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the BM25 sparse model at build time so the container starts
# without needing network access at runtime.
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')"

# Pre-download the FlashRank cross-encoder ONNX model (~20MB) at build time
# so the first user query doesn't incur a cold-download delay.
RUN python -c "from flashrank import Ranker; Ranker()"

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python -m alembic upgrade heads && uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]