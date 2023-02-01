# ./build_all_images.sh builds this as pmc-crawler:latest
FROM python:3.10

RUN apt update && apt install -y nodejs

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install
COPY . ./

ENTRYPOINT ["/app/entrypoint.sh"]
