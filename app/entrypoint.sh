#!/bin/bash

mkdir -p /app/_build
mkdir -p /app/_output

TARGET_NOTEBOOK=${TARGET_NOTEBOOK:-"Create Cites from PMC Lookups - Monthly.ipynb"}

# debugging
echo "--- Starting the PMC crawler with the following parameters:"
echo "* START_DATE: ${START_DATE}"
echo "* END_DATE: ${END_DATE}"
echo "* AUTHORS_SHEET_ID: ${AUTHORS_SHEET_ID}"
echo "* DEPARTMENT: ${DEPARTMENT}"
echo "---"

cd /app/notebooks && \
poetry run papermill \
    --no-report-mode \
    --log-output \
    -r start_date "${START_DATE}" \
    -r end_date "${END_DATE}" \
    -r authors_sheet_id "${AUTHORS_SHEET_ID}" \
    -r department "${DEPARTMENT}" \
    "${TARGET_NOTEBOOK}" \
    "/app/_output/${TARGET_NOTEBOOK}"  
