#!/bin/bash
# Generate self-signed TLS certificates for local development
set -e
CERT_DIR="${1:-./certs}"
mkdir -p "$CERT_DIR"
openssl req -x509 -newkey rsa:4096 -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" -days 365 -nodes -subj "/CN=localhost/O=LocalDev"
echo "Certificates generated in $CERT_DIR"
