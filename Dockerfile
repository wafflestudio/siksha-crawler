# ----- python-base ----- #
FROM python:3.10.11-slim-bullseye AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_NO_INTERACTION=1

# ----- builder-base ----- #
FROM python-base AS builder-base

RUN pip install poetry==1.5.0

WORKDIR /app

COPY poetry.lock pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/poetry \
    poetry install --without dev

# ----- runtime ----- #
FROM python-base AS runtime

ARG DB_HOST
ARG DB_NAME
ARG DB_USER
ARG DB_PASSWORD
ARG SLACK_TOKEN
ARG SLACK_CHANNEL

ENV DB_HOST=$DB_HOST \
    DB_NAME=$DB_NAME \
    DB_USER=$DB_USER \
    DB_PASSWORD=$DB_PASSWORD \
    SLACK_TOKEN=$SLACK_TOKEN \
    SLACK_CHANNEL=$SLACK_CHANNEL

ENV VENV_PATH="/app/.venv" \
    PATH="$VENV_PATH/bin:$PATH"

COPY --from=builder-base $VENV_PATH $VENV_PATH

WORKDIR /app

COPY . .

EXPOSE 8000

CMD ["python", "handler.py"]
