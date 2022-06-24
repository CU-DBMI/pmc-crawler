# smartsheet-notebooks

Center-specific notebook logic, mostly with MDC data

# Requirements

This uses the poetry tool.

# Install Poetry

    In my environment I run entirely "path-less", with a number of scripts for each version of Python (e.g python39.cmd, python310.cmd). After each of those scripts is run, I install poetry in each, and proceed from there. Your experience may/will vary.

    pip install poetry

# To work in notebooks

    poetry run jupyter notebook

# To run a notebook on the command line

Note, the `_output` folder must already exist.

    # from the source folder
    cd smartsheet-notebooks
    
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
