FROM alpine:3.22

RUN apk add --no-cache openssh-client \
    && addgroup -g 1000 tunnel \
    && adduser -D -u 1000 -G tunnel tunnel

ENV HOME=/home/tunnel

ENTRYPOINT ["ssh"]
