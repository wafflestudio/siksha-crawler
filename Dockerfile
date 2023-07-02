FROM python:3.10

ARG DB_HOST
ARG DB_NAME
ARG DB_USER
ARG DB_PASSWORD
ARG SLACK_TOKEN
ARG SLACK_CHANNEL

ENV DB_HOST $DB_HOST
ENV DB_PORT 3306
ENV DB_NAME $DB_NAME
ENV DB_USER $DB_USER
ENV DB_PASSWORD $DB_PASSWORD
ENV SLACK_TOKEN $SLACK_TOKEN
ENV SLACK_CHANNEL $SLACK_CHANNEL

COPY . /siksha-crawler
WORKDIR /siksha-crawler

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt


CMD ["python", "handler.py"]
