# ./build_all_images.sh builds this as pmc-crawler:latest
FROM python:3.10

# RUN apt update && apt install -y nodejs
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - &&\
    apt-get install -y nodejs

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install
RUN pip install jupyterlab-git
COPY . ./

ENTRYPOINT ["/app/entrypoint.sh"]
