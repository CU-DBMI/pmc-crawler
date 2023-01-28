# PMC Citation Crawler

Center-specific notebook logic, mostly with MDC data

# Requirements

You'll need Docker installed, which you can obtain for your platform here:
https://www.docker.com/products/docker-desktop/

Alternatively, you can run the project outside of a Docker container, in which
case you'll need [Poetry](https://python-poetry.org/), a Python packaging and dependency manager.

# To work in notebooks

    poetry run jupyter notebook

# To run a notebook on the command line

Note, the `_output` folder must already exist.

    # from the source folder
    cd notebooks
    
    poetry run papermill --no-report-mode --log-output "smartsheet Set Task Integration Status.ipynb" "_output\smartsheet Set Task Integration Status.ipynb" 

# Secrets and keys

Keys for MDC and SS are kept in files called `.env-<environment>`, where environment is a parameter passed into the notebook. For example, the environment variable file for `dev` is `.env-dev`. These files are located in the same folder as the notebooks.

## Example .env file

```
SMARTSHEET_KEY=123980123890123980
```

## Cleaning and Linting with Dagger

Development may be assisted using [Dagger](https://docs.dagger.io/) and related files within this repo. Use the following steps to get started:

1. [Install Dagger](https://docs.dagger.io/1200/local-dev)
1. Open a terminal and navigate to the directory of this source.
1. Use `dagger project update` to populate dependencies.
1. Use the following to clean, lint, or test with Dagger:
    - Clean: `dagger do clean` (perform various auto-formatting on notebooks)
    - Lint: `dagger do lint` (perform various linting on notebooks and project)
