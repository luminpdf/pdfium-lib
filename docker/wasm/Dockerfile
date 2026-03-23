FROM ubuntu:22.04

# general
ARG DEBIAN_FRONTEND=noninteractive

ENV PROJ_TARGET="wasm"

ENV JAVA_VERSION="8"
ENV JAVA_HOME="/usr/lib/jvm/java-8-openjdk-amd64/"

ENV PYTHONIOENCODING="utf8"
ENV LC_ALL=C.UTF-8

# packages
RUN apt-get -y update && \
    apt-get install -y build-essential sudo file git wget curl cmake ninja-build zip unzip tar python3 python3-pip nano lsb-release libglib2.0-dev tzdata doxygen python3-setuptools --no-install-recommends
RUN echo '#!/bin/bash\nexit 0' > /usr/local/bin/keytool && chmod +x /usr/local/bin/keytool && \
    apt-get install -y --no-install-recommends openjdk-${JAVA_VERSION}-jdk && \
    rm -f /usr/local/bin/keytool && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# define timezone
RUN echo "America/Sao_Paulo" > /etc/timezone
RUN dpkg-reconfigure -f noninteractive tzdata
RUN /bin/echo -e "LANG=\"en_US.UTF-8\"" > /etc/default/local

# java
ENV PATH=${PATH}:${JAVA_HOME}/bin
RUN echo ${JAVA_HOME}
RUN java -version

# google depot tools
ENV DEPOT_TOOLS_UPDATE=0
ENV DEPOT_TOOLS_WIN_TOOLCHAIN=0
RUN git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git -b main /opt/depot-tools
ENV PATH=${PATH}:/opt/depot-tools

# pdfium - copy local source and sync only dependencies via gclient
RUN mkdir /build
WORKDIR /build

# copy local pdfium source (must exist in docker build context as ./pdfium)
COPY ./pdfium /build/pdfium

# initialize a temporary git repo to satisfy gclient --unmanaged requirement
# remove the submodule .git pointer file first so git init works cleanly
RUN rm -f /build/pdfium/.git && \
    git -C /build/pdfium init && \
    git -C /build/pdfium config user.email "build@local" && \
    git -C /build/pdfium config user.name "build" && \
    git -C /build/pdfium add . && \
    git -C /build/pdfium commit -m "local-build-sync"

# configure gclient to use the local (unmanaged) source and sync only dependencies
RUN gclient config --custom-var checkout_configuration=minimal --unmanaged pdfium
RUN echo "target_os = [ 'emscripten' ]" >> .gclient
RUN gclient sync --no-history --shallow

# preserve pdfium source at /pdfium before cleaning /build
# pdfium.py resolves: /app/modules/../../pdfium = /pdfium
RUN cp -r /build/pdfium /pdfium

# system dependencies
RUN ln -s /usr/bin/python3 /usr/bin/python

RUN apt update -y \
    && echo n | /build/pdfium/build/install-build-deps.sh || true \
    && rm -rf /build

# ninja
RUN ln -nsf /opt/depot-tools/ninja-linux64 /usr/bin/ninja

# dependencies
RUN pip3 install --upgrade pip
RUN pip3 install setuptools docopt pygemstones

# emsdk
RUN mkdir /emsdk
WORKDIR /emsdk
RUN git clone https://github.com/emscripten-core/emsdk.git .
RUN ./emsdk install 4.0.15
RUN ./emsdk activate 4.0.15
ENV PATH="${PATH}:/emsdk:/emsdk/upstream/emscripten"

# cache system libraries
RUN bash -c 'echo "int main() { return 0; }" > /tmp/main.cc'
RUN bash -c 'source /emsdk/emsdk_env.sh && em++ -s USE_ZLIB=1 -s USE_LIBJPEG=1 -s USE_PTHREADS=1 -s ASSERTIONS=1 -o /tmp/main.html /tmp/main.cc'

# nodejs and npm
RUN curl -sL https://deb.nodesource.com/setup_22.x | bash -
RUN apt-get install -y nodejs
RUN npm install -g npm@latest

# working dir
WORKDIR /app
