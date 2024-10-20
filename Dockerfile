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

COPY static/ /app/static/
COPY templates/ /app/templates/
COPY favicon.ico /app/favicon.ico
COPY *.py /app/

WORKDIR /app
CMD python -m server