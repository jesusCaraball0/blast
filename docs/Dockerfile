FROM python:3.11.13

# Needed to compile fsps (Fortran) + other native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gfortran \
    build-essential \
    cmake \
    ninja-build \
    git \
    && rm -rf /var/lib/apt/lists/*

# (Optional but recommended) keep pip tooling current for pyproject builds
RUN python -m pip install --upgrade pip setuptools wheel

## Install Python dependencies
COPY docs/requirements.txt /tmp/docs-requirements.txt
RUN pip install --no-cache-dir -r /tmp/docs-requirements.txt
COPY app/requirements.txt /tmp/app-requirements.txt
RUN pip install --no-cache-dir -r /tmp/app-requirements.txt
