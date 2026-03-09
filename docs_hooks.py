"""MkDocs build hook: replace the generated index.html with the custom landing page."""

import os
import shutil


def on_post_build(config: dict) -> None:
    site_dir = config["site_dir"]
    shutil.copy("landing/index.html", os.path.join(site_dir, "index.html"))
    shutil.copy("landing/landing.css", os.path.join(site_dir, "landing.css"))
