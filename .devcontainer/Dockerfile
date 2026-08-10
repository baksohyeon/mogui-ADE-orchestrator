FROM mcr.microsoft.com/vscode/devcontainers/python:1-3.12-bookworm

ARG GITLEAKS_VERSION=8.30.1
ARG TARGETARCH

RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) gitleaks_arch='x64'; gitleaks_sha='551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb' ;; \
      arm64) gitleaks_arch='arm64'; gitleaks_sha='e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080' ;; \
      *) echo "unsupported Docker architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    package="gitleaks_${GITLEAKS_VERSION}_linux_${gitleaks_arch}.tar.gz"; \
    curl --fail --silent --show-error --location \
      --output "/tmp/${package}" \
      "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${package}"; \
    echo "${gitleaks_sha}  /tmp/${package}" | sha256sum --check --strict; \
    tar --extract --gzip --file "/tmp/${package}" --directory /tmp gitleaks; \
    install --directory --mode 0755 /opt/gitleaks/bin; \
    install --mode 0755 /tmp/gitleaks /opt/gitleaks/bin/gitleaks; \
    rm -f "/tmp/${package}" /tmp/gitleaks

RUN python -m pip install --no-cache-dir pytest

ENV PATH="/opt/gitleaks/bin:${PATH}"

WORKDIR /workspaces/mogui-ADE-orchestrator
