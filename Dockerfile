FROM python:3
MAINTAINER Jean-Tiare Le Bigot <jt@yadutaf.fr>

WORKDIR /src
ADD . /src
RUN python ./setup.py install

CMD ["ctop"]

