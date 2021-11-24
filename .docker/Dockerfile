ARG QGIS_TEST_VERSION=latest
FROM  qgis/qgis:${QGIS_TEST_VERSION}

RUN apt-get update && \
    apt-get install -y python3-pip
COPY ./requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

COPY ./requirements_test.txt /tmp/
RUN pip3 install -r /tmp/requirements_test.txt

RUN apt-get install wget
RUN wget -nv https://github.com/koordinates/kart/releases/download/v0.10.7/kart_0.10.7-1_amd64.deb
RUN apt install -q ./kart_0.10.7-1_amd64.deb

ENV LANG=C.UTF-8

WORKDIR /
