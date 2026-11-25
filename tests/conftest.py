"""Shared test fixtures.

`previous_forms`: the approval, profile, import and newsletter tests are about how the application treats entries, not about the wording of a
particular form. They run on a frozen copy of the earlier form definitions (tests/fixtures/previous_forms), so a new edition of the Google
Forms does not mean rewriting them. The forms the application ships now are tested in test_it_matrix_forms.py.
"""
import gc
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))



@pytest.fixture(autouse=True, scope="session")
def _a_copy_of_the_newsletter_database(tmp_path_factory):
    """The studio keeps its entries in step with the master database, so no test may point it at the project's own newsletter database."""
    from database import db_manager
    copy = str(tmp_path_factory.mktemp("newsletter") / "newsletter.db")
    if os.path.exists(db_manager.DB_PATH):
        shutil.copyfile(db_manager.DB_PATH, copy)
    before, db_manager.DB_PATH = db_manager.DB_PATH, copy
    yield
    db_manager.DB_PATH = before


PREVIOUS = os.path.join(os.path.dirname(__file__), "fixtures", "previous_forms")


@pytest.fixture(scope="module")
def previous_forms():
    from backend import app as _app  # noqa: F401  (creates the long-lived services whose file paths are redirected below)
    from backend.master import definitions
    from backend.services import config_service, normalization_service
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(definitions, "SPEC_FILE", os.path.join(PREVIOUS, "master_forms.json"))
        mp.setattr(definitions, "SECTIONS_FILE", os.path.join(PREVIOUS, "section_categories.json"))
        mp.setattr(normalization_service, "CONFIG_DIR", PREVIOUS)
        for obj in gc.get_objects():
            if type(obj).__name__ in ("NormalizationService", "ConfigService") and hasattr(obj, "mappings_file"):
                mp.setattr(obj, "mappings_file", os.path.join(PREVIOUS, "form_mappings.json"))
                if hasattr(obj, "_mtime"):
                    mp.setattr(obj, "_mtime", None)
                if hasattr(obj, "sections_file"):
                    mp.setattr(obj, "sections_file", os.path.join(PREVIOUS, "section_categories.json"))
                if hasattr(obj, "mappings"):
                    import json
                    mp.setattr(obj, "mappings", json.load(open(os.path.join(PREVIOUS, "form_mappings.json"), encoding="utf-8")))
        definitions._cache.clear()
        yield
    definitions._cache.clear()
