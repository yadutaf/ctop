FROM python:2-alpine
MAINTAINER Jean-Tiare Le Bigot <jt@yadutaf.fr>

# Ctop is a single file programa. Just copy it
COPY cgroup_top.py /app/

ENTRYPOINT ["python", "/app/cgroup_top.py"]
CMD []

