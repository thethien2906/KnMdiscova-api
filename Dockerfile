FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app
RUN mkdir -p /app/staticfiles /app/media && \
    adduser \
        --system \
        --group \
        --disabled-password \
        --no-create-home \
        django-user

COPY ./requirements.txt /tmp/requirements.txt
COPY ./requirements.dev.txt /tmp/requirements.dev.txt

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        cmake \
        # Add any other build dependencies specific to dlib/opencv if they become apparent
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /py && \
    /py/bin/pip install --upgrade pip && \
    # Install setuptools and wheel first
    /py/bin/pip install setuptools wheel && \
    /py/bin/pip install -r /tmp/requirements.txt && \
    if [ "$DEV" = "true" ]; then \
        /py/bin/pip install -r /tmp/requirements.dev.txt; \
    fi && \
    rm -rf /tmp

COPY ./app /app
RUN chown -R django-user:django-user /app
ENV PATH="/py/bin:$PATH"
USER django-user