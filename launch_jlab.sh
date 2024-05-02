#!/usr/bin/env bash

JLAB_PORT=8810

DOCKER_NETWORK="pmc-crawler"

docker network create pmc-crawler || echo "* Network '${DOCKER_NETWORK}' already exists, skipping creation..."

# ensure the format converter container is running
if ! ( docker ps | grep reformed >/dev/null 2>&1 ); then
    echo "* Reformed isn't running, booting it now..."
    docker run -d --name reformed \
        -p 8088:8000 --network ${DOCKER_NETWORK} \
        ghcr.io/davidlougheed/reformed:sha-1b8f46b
fi

# remove the previous container, if it exists
( docker rm --force pmc-crawler-jlab 2>/dev/null )

docker run --name pmc-crawler-jlab \
    --rm -it \
    -p ${JLAB_PORT}:${JLAB_PORT} \
    --network ${DOCKER_NETWORK} \
    -v $PWD/app:/app \
    --env-file ./app/.env \
    --entrypoint='/bin/bash' \
    pmc-crawler:latest \
    -c "/usr/local/bin/poetry run jupyter lab --no-browser --allow-root --ip=0.0.0.0 --port=${JLAB_PORT}"
