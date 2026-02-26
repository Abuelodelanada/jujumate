import nox

nox.options.default_venv_backend = "uv"


@nox.session
def tests(session: nox.Session) -> None:
    session.install(".[dev]", "pytest", "pytest-asyncio", "pytest-cov")
    session.run("coverage", "erase")
    session.run("pytest", "--cov=jujumate", "--cov-report=term-missing", *session.posargs)


@nox.session
def lint(session: nox.Session) -> None:
    session.install("ruff")
    session.run("ruff", "check", "src", "tests")
    session.run("ruff", "format", "--check", "src", "tests")


@nox.session
def typecheck(session: nox.Session) -> None:
    session.install(".", "pyright")
    session.run("pyright", "src")
