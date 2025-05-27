FROM python:3.9-slim
LABEL maintainer="minjire"
ENV PYTHONUNBUFFERED 1

COPY ./requirements.txt /tmp/requirements.txt
COPY ./requirements.dev.txt /tmp/requirements.dev.txt
COPY ./app /app
WORKDIR /app
EXPOSE 8000

ARG DEV=false

# Install system dependencies (Debian/Ubuntu packages instead of Alpine)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        libc6-dev \
        libpq-dev \
        build-essential \
        curl \
        git && \
    python -m venv /py && \
    /py/bin/pip install --upgrade pip setuptools wheel

# Install protobuf and grpc with compatible versions
RUN /py/bin/pip install --no-cache-dir \
    "protobuf>=4.21.6,<5.0.0" \
    "grpcio>=1.50.0,<1.63.0" \
    "grpcio-tools>=1.50.0,<1.63.0"

# Install Modal with compatible protobuf version
RUN /py/bin/pip install --no-cache-dir "modal>=0.63.0"

# Install main requirements
RUN /py/bin/pip install -r /tmp/requirements.txt

# Install dev requirements if needed
RUN if [ $DEV = "true" ] ; \
        then echo "--DEV BUILD--" && /py/bin/pip install -r /tmp/requirements.dev.txt ; \
    fi

# Clean up
RUN apt-get purge -y --auto-remove \
        gcc \
        libc6-dev \
        build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*

# Create logs directory
RUN mkdir -p /app/logs

# Add user (same as your original)
RUN adduser \
        --disabled-password \
        --no-create-home \
        django-user

# Change ownership of app directory
RUN chown -R django-user:django-user /app

ENV PATH="/py/bin:$PATH"

USER django-user