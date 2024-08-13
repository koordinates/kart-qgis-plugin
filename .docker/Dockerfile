ARG QGIS_TEST_VERSION=latest
FROM qgis/qgis:${QGIS_TEST_VERSION}

ENV PIP_BREAK_SYSTEM_PACKAGES 1

RUN apt-get update && \
    apt-get install -y python3-pip
COPY ./requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

COPY ./requirements_test.txt /tmp/
RUN pip3 install -r /tmp/requirements_test.txt

ARG KART_VERSION
RUN apt-get install -y wget
RUN wget -nv https://github.com/koordinates/kart/releases/download/v${KART_VERSION}/kart_${KART_VERSION}_$(dpkg --print-architecture).deb
RUN apt install -qy ./kart_${KART_VERSION}_$(dpkg --print-architecture).deb
#RUN kart --version

ENV LANG=C.UTF-8

WORKDIR /
