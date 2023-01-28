# ./build_all_images.sh builds this as pmc-crawler:latest
FROM python:3.10

RUN pip install poetry

WORKDIR /app

COPY poetry.lock pyproject.toml ./
RUN poetry install
COPY . ./

ENTRYPOINT ["/app/entrypoint.sh"]
