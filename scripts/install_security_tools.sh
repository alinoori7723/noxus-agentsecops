#!/usr/bin/env bash
set -euo pipefail
TOOLS_DIR="${1:?Provide a tool installation directory}"
mkdir -p "$TOOLS_DIR"
TOOLS_DIR="$(cd "$TOOLS_DIR" && pwd)"
DOWNLOAD_DIR="$(mktemp -d)"
trap 'rm -rf "$DOWNLOAD_DIR"' EXIT
cd "$DOWNLOAD_DIR"
curl --fail --location --proto '=https' --tlsv1.2 --retry 3 -o gitleaks.tar.gz https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz
echo '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb  gitleaks.tar.gz' | sha256sum --check
curl --fail --location --proto '=https' --tlsv1.2 --retry 3 -o trivy.tar.gz https://github.com/aquasecurity/trivy/releases/download/v0.74.0/trivy_0.74.0_Linux-64bit.tar.gz
echo '2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a  trivy.tar.gz' | sha256sum --check
tar -xzf gitleaks.tar.gz -C "$TOOLS_DIR" gitleaks
tar -xzf trivy.tar.gz -C "$TOOLS_DIR" trivy
