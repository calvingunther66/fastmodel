#!/usr/bin/env bash
# Best-effort setup for the schedule extractor prototype.
#
# - Installs the Tesseract OCR engine (needed only for image-based sheets).
# - Installs the Python dependencies.
#
# If the environment blocks apt/network, the cell-extraction path still works
# once the pip dependencies are installed; OCR simply degrades gracefully.
set -u

echo "==> Installing Tesseract OCR engine (best-effort)..."
if command -v tesseract >/dev/null 2>&1; then
  echo "    tesseract already installed: $(tesseract --version 2>&1 | head -1)"
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y tesseract-ocr \
    || echo "    WARNING: could not install tesseract; OCR of image sheets will be skipped."
else
  echo "    WARNING: apt-get not available; install tesseract manually for OCR support."
fi

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Done."
