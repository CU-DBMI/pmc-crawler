#!/usr/bin/env bash

JLAB_PORT=8888

docker run \
    --rm -it -p ${JLAB_PORT}:${JLAB_PORT} \
    --network host \
    -v $PWD/app:/app \
    --env-file ./app/.env \
    --entrypoint='/bin/bash' \
    pmc-crawler:latest \
    -c "/usr/local/bin/poetry run jupyter lab --no-browser --allow-root --ip=0.0.0.0 --port=${JLAB_PORT}"
