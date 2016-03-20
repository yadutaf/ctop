FROM python:2-alpine
MAINTAINER Jean-Tiare Le Bigot <jt@yadutaf.fr>

ENTRYPOINT ["ctop"]
CMD []

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

WORKDIR /app
COPY . /app/
RUN pip install .
