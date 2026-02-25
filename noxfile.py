import nox

nox.options.default_venv_backend = "uv"


@nox.session
def tests(session: nox.Session) -> None:
    session.install(".[dev]", "pytest", "pytest-asyncio")
    session.run("pytest", *session.posargs)
