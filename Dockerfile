FROM python:3.12-slim

ENV PORT=3000
EXPOSE 3000

# Install necessary build tools
# RUN apt-get update && apt-get install -y \
#     build-essential \
#     gcc \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt
# --extra-index-url https://download.pytorch.org/whl/cpu

COPY templates/ /app/templates/
COPY server.py /app/server.py

WORKDIR /app
CMD python -m server