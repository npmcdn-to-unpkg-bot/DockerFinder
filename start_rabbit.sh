#!/usr/bin/env bash

docker run --net=core-net --hostname rabbitmq -p 8081:15672 rabbitmq:3-management
