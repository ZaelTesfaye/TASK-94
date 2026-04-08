# Generate self-signed TLS certificates for local development
param([string]$CertDir = "./certs")
New-Item -ItemType Directory -Force -Path $CertDir | Out-Null
openssl req -x509 -newkey rsa:4096 -keyout "$CertDir/key.pem" -out "$CertDir/cert.pem" -days 365 -nodes -subj "/CN=localhost/O=LocalDev"
Write-Host "Certificates generated in $CertDir"
