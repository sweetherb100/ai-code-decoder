"""Third-party packages whose official documentation can be cited.

Only packages listed here are looked up. Names of unlisted packages (which can be
private) never leave the app. Every entry points at the package's own docs site
and a machine-readable symbol index, verified on 2026-10-25.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IndexKind = Literal["sphinx_inventory", "llms_txt"]


@dataclass(frozen=True)
class PackageDocs:
    """Where a package's official documentation and symbol index live."""

    project: str
    docs_url: str
    index_kind: IndexKind
    index_url: str
    # llms.txt indexes name symbols by their conventional alias (`st.title`).
    index_root: str = ""


def _sphinx(project: str, docs_url: str, index_url: str = "") -> PackageDocs:
    return PackageDocs(project, docs_url, "sphinx_inventory", index_url or docs_url + "objects.inv")


# Keyed by top-level import name, which can differ from the PyPI name.
PACKAGE_DOCS: dict[str, PackageDocs] = {
    "bs4": _sphinx("Beautiful Soup", "https://www.crummy.com/software/BeautifulSoup/bs4/doc/"),
    "click": _sphinx("Click", "https://click.palletsprojects.com/en/stable/"),
    "django": _sphinx(
        "Django",
        "https://docs.djangoproject.com/en/stable/",
        "https://docs.djangoproject.com/en/stable/_objects/",
    ),
    "dotenv": _sphinx("python-dotenv", "https://saurabh-kumar.com/python-dotenv/"),
    "fastapi": _sphinx("FastAPI", "https://fastapi.tiangolo.com/"),
    "flask": _sphinx("Flask", "https://flask.palletsprojects.com/en/stable/"),
    "matplotlib": _sphinx("Matplotlib", "https://matplotlib.org/stable/"),
    "numpy": _sphinx("NumPy", "https://numpy.org/doc/stable/"),
    "pandas": _sphinx("pandas", "https://pandas.pydata.org/docs/"),
    "PIL": _sphinx("Pillow", "https://pillow.readthedocs.io/en/stable/"),
    "pydantic": _sphinx("Pydantic", "https://docs.pydantic.dev/latest/"),
    "pytest": _sphinx("pytest", "https://docs.pytest.org/en/stable/"),
    "requests": _sphinx("Requests", "https://requests.readthedocs.io/en/latest/"),
    "scipy": _sphinx("SciPy", "https://docs.scipy.org/doc/scipy/"),
    "sqlalchemy": _sphinx("SQLAlchemy", "https://docs.sqlalchemy.org/en/20/"),
    "streamlit": PackageDocs(
        "Streamlit",
        "https://docs.streamlit.io/",
        "llms_txt",
        "https://docs.streamlit.io/llms.txt",
        index_root="st",
    ),
}


def registered_package(module: str) -> PackageDocs | None:
    """Return the registry entry for a module's top-level package, if any."""
    return PACKAGE_DOCS.get(module.split(".", 1)[0])
