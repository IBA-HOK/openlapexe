"""Harness entry: pytest pythonpath and src layout smoke."""

def test_import_vehicle() -> None:
    import openlapexe.vehicle  # noqa: F401

    assert openlapexe.vehicle is not None


def test_import_track() -> None:
    import openlapexe.track  # noqa: F401

    assert openlapexe.track is not None
