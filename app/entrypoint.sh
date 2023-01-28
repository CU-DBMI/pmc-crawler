#!/bin/bash

mkdir -p /app/_build
mkdir -p /app/_output

TARGET_NOTEBOOK=${TARGET_NOTEBOOK:-"Create Cites from PMC Lookups - Monthly.ipynb"}

cd /app/notebooks && \
poetry run papermill \
    --no-report-mode \
    --log-output \
    -r start_date ${START_DATE} \
    -r end_date ${END_DATE} \
    "${TARGET_NOTEBOOK}" \
    "/app/_output/${TARGET_NOTEBOOK}"  
