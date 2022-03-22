FROM python:3.10-slim
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV PYTHONDONTWRITEBYTECODE 1 # prevent writing .pyc files to disc
ENV PYTHONUNBUFFERED 1 # prevent buffering stdout and stderr
EXPOSE 5000

COPY . .

RUN pip install -r requirements.txt