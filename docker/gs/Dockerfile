ARG PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim-bookworm
FROM ${PYTHON_BASE_IMAGE} AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

ARG APT_MIRROR_URL=
ARG PIP_INDEX_URL=
ARG PIP_EXTRA_INDEX_URL=

RUN if [ -n "${APT_MIRROR_URL}" ]; then \
        find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec sed -i \
            -e "s|http://deb.debian.org/debian|${APT_MIRROR_URL}/debian|g" \
            -e "s|https://deb.debian.org/debian|${APT_MIRROR_URL}/debian|g" \
            -e "s|http://deb.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            -e "s|https://deb.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            -e "s|http://security.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            -e "s|https://security.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            {} +; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cargo \
        libffi-dev \
        libssl-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN python -m venv /opt/venv \
    && if [ -n "${PIP_INDEX_URL}" ]; then export PIP_INDEX_URL="${PIP_INDEX_URL}"; fi \
    && if [ -n "${PIP_EXTRA_INDEX_URL}" ]; then export PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}"; fi \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

FROM ${PYTHON_BASE_IMAGE} AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/genesis

ARG APT_MIRROR_URL=

RUN if [ -n "${APT_MIRROR_URL}" ]; then \
        find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec sed -i \
            -e "s|http://deb.debian.org/debian|${APT_MIRROR_URL}/debian|g" \
            -e "s|https://deb.debian.org/debian|${APT_MIRROR_URL}/debian|g" \
            -e "s|http://deb.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            -e "s|https://deb.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            -e "s|http://security.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            -e "s|https://security.debian.org/debian-security|${APT_MIRROR_URL}/debian-security|g" \
            {} +; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        qrencode \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY genesis ./genesis
COPY config.yaml.example ./config.yaml.example
COPY docker/gs/entrypoint.sh /usr/local/bin/gs-entrypoint

RUN chmod +x /usr/local/bin/gs-entrypoint \
    && ln -s /usr/local/bin/gs-entrypoint /usr/local/bin/gs

VOLUME ["/var/lib/gs"]

EXPOSE 19840/udp
EXPOSE 19841/tcp
EXPOSE 19842/tcp

STOPSIGNAL SIGTERM

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/gs-entrypoint"]
CMD ["start"]
