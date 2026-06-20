Standartized DS project template
==============================

Project Organization
------------

    ├── Makefile           <- Makefile with commands like `make data` or `make train`
    ├── README.md          <- The top-level README for developers using this project.
    ├── pyproject.toml     <- Project configuration for dependencies, linting, formatting, etc.
    ├── uv.lock            <- The lock file for reproducing the analysis environment.
    ├── data
    │   ├── external       <- Data from third party sources.
    │   ├── interim        <- Intermediate data that has been transformed.
    │   ├── processed      <- The final, canonical data sets for modeling.
    │   └── raw            <- The original, immutable data dump.
    │
    ├── models             <- Trained and serialized models, model predictions, or model summaries
    │
    ├── notebooks          <- Jupyter notebooks. Naming convention is a number (for ordering),
    │                         the creator's initials, and a short `-` delimited description, e.g.
    │                         `1.0-jqp-initial-data-exploration`.
    │
    ├── references         <- Data dictionaries, manuals, and all other explanatory materials.
    │
    ├── reports            <- Generated analysis as HTML, PDF, LaTeX, etc.
    │   └── figures        <- Generated graphics and figures to be used in reporting
    │
    └── src                <- Source code for use in this project.
        ├── __init__.py    <- Makes src a Python module
        │
        ├── data           <- Scripts to download or generate data
        │
        ├── features       <- Scripts to turn raw data into features for modeling
        │
        ├── models         <- Scripts to train models and then use trained models to make
        │   │                 predictions
        │
        └── visualization  <- Scripts to create exploratory and results oriented visualizations


Logging
-------

This project provides a general-purpose logger utility in `src/utils/logger.py`.

**Usage Example:**

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("This is an info message.")
logger.error("This is an error message.")
```

You can attach this logger to any module or script in the project.

--------

## Goals
- Reduce time to establish a repo specifically for DS needs.
- To align data scientists in terms of skills and tools used.
- Make project standard, easier to observe and predictable.

## Description:

### Project structure

The current architecture is based on [Cookiecutter DS](https://github.com/drivendata/cookiecutter-data-science) approach. The reasoning behind it you can find [here](http://drivendata.github.io/cookiecutter-data-science/).

### Code versioning tools
To track, keep and share your codings [git](https://git-scm.com/) and [GitHub](https://github.com/) services are required.

### Default programming language
To leverage modern programming stack it is recommended to start with [Python 3.13](https://www.python.org/downloads/release/python-3130/) as default.

### Dependency management
To follow Single-Source-Of-Truth concept it makes sense to use [pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) to store project configuration. `pyproject.toml` configuration file allows to use the same configuration on different project steps: CI/CD, dev, test, prod etc.

#### uv
Newly announced [uv tool](https://github.com/astral-sh/uv).

To create new virtual environment:
```bash
uv venv -p 3.13
```

You might need to install or provide path to python 3.13 first.

Activate an environment on macOS and Linux:
```bash
source .venv/bin/activate
```

On Windows:
```shell
.venv\Scripts\activate
```

To install dependencies from `pyproject.toml` (and `uv.lock`):
```bash
uv pip sync --extra dev --extra lint --extra test
```

To update `uv.lock` file:
```bash
uv lock --upgrade
```

### Codestyle: ruff
Both for code linting and formatting Ruff package is proposed to use. See [here](https://docs.astral.sh/ruff/) for more details.

Commands:
```bash
ruff format .
ruff check .

ruff check . --fix
```

### CI/CD: GitHub Actions

As a baseline, CI with integrated code style is provided (see `.github/workflows/ci.yml`). The current setup is based on using public Actions and configuring CI with `pyproject.toml` file. It is also possible to use custom Actions.

### Test suite: pytest

This project uses [pytest](https://docs.pytest.org/en/stable/) for running tests and [pytest-cov](https://pytest-cov.readthedocs.io/en/latest/) for measuring test coverage.

To run the tests and generate a coverage report, use the following commands:

```bash
coverage run -m pytest -v .
coverage report -m
```

The CI is configured to fail if the test coverage is below 80%.


## Getting started
1. Create repo from the template

While creating repo, choose the current one as a template. Check [tutorial](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository) for more details.

It is also possible to use this repository as a template in GitHub interface.

2. Install, compile and activate virtual environment
See [uv](#uv)

3. Change parameters `pyproject.toml` if needed.
4. Tweak CI configuration `.github/workflows/ci.yml` if needed.
5. Put you source code in `src` folder.
6. Enjoy coding :)

## Best practices

### Makefile
Codestyle functionality could be applied locally using the Makefile created and the following command:

```bash
make precommit
```

or using `.sh` file directly:

```bash
bash ./precommit.sh
```
