#!/usr/bin/env bash

JLAB_PORT=8888

# ensure the format converter container is running
if ! ( docker ps | grep reformed >/dev/null 2>&1 ); then
    echo "* Reformed isn't running, booting it now..."
    docker run -d --name reformed -p 8088:8000 ghcr.io/davidlougheed/reformed:sha-1b8f46b
fi

t_first_date=$(date +%Y/%m/01)
t_last_date=$(date -d "`date +%Y%m01` +1 month -1 day" +%Y/%m/%d)

# ---------------------------------------
# --- step 1. prompt for run parameters
# ---------------------------------------

# pre-step: extract params from the .env file, if available
ENV_FILE="./app/.env"
if [ -f "${ENV_FILE}" ]; then
    ENV_AUTHORS_SHEET_ID=$( cat ${ENV_FILE} | grep -e '^AUTHORS_SHEET_ID' | cut -d'=' -f2 )
    ENV_DEPARTMENT=$( cat ${ENV_FILE} | grep -e '^DEPARTMENT' | cut -d'=' -f2 )
fi

START_DATE=${START_DATE:-${t_first_date}}
END_DATE=${END_DATE:-${t_last_date}}
AUTHORS_SHEET_ID=${AUTHORS_SHEET_ID:-${ENV_AUTHORS_SHEET_ID:-""}}
DEPARTMENT=""

read -p "- Enter start date [${START_DATE}]: " INPUT_START_DATE
START_DATE=${INPUT_START_DATE:-${START_DATE}}

read -p "- Enter end date [${END_DATE}]: " INPUT_END_DATE
END_DATE=${INPUT_END_DATE:-${END_DATE}}

if [ -z ${AUTHORS_SHEET_ID} ]; then
    # if it's unset, give them a chance to set it
    read -p "- Enter smartsheet ID for authors' sheet [${AUTHORS_SHEET_ID}]: " INPUT_AUTHORS_SHEET_ID
    AUTHORS_SHEET_ID=${INPUT_AUTHORS_SHEET_ID:-${AUTHORS_SHEET_ID}}
else
    # it was in the env file, so let the user know
    echo "* Got AUTHORS_SHEET_ID from .env file: ${AUTHORS_SHEET_ID}"
fi

read -p "- Enter department (a blank value disables this filter): " INPUT_DEPARTMENT
DEPARTMENT=${INPUT_DEPARTMENT:-""}

# check for required values
if [ -z ${AUTHORS_SHEET_ID} ] || [ ${AUTHORS_SHEET_ID} -eq "-1" ]; then
    echo "ERROR: author sheet ID required (given: '${AUTHORS_SHEET_ID}'), exiting"
    exit 1
fi

# -------------------------------------------------------------------
# --- step 2. start the run with the entered params, storing artifacts in ./output
# -------------------------------------------------------------------

mkdir -p output
mkdir -p intermediate

time (
    docker run --name pmc-crawler \
        --rm -it \
        --network host \
        -e START_DATE=${START_DATE} \
        -e END_DATE=${END_DATE} \
        -e AUTHORS_SHEET_ID=${AUTHORS_SHEET_ID} \
        -e DEPARTMENT=${DEPARTMENT} \
        -v $PWD/app:/app \
        -v $PWD/output:/app/_build \
        -v $PWD/intermediate:/app/_output \
        --env-file ./app/.env \
        pmc-crawler:latest
)