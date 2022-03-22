The following docker-compose command creates containers with the following:
- Gunicorn flask server: default worker count is one
- Locust: Distributed setup containing one master and 3 worker nodes. Scale according to your needs
```
docker-compose up --build --scale locust-worker=3
```
