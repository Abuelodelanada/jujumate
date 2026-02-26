from jujumate.app import JujuMateApp
from jujumate.log import setup_logging
from jujumate.settings import load_settings


def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    JujuMateApp().run()
