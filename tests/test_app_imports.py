"""Smoke: app imports and exposes expected symbols."""

def test_app_imports() -> None:
    import app

    assert hasattr(app, "resource_path")
    assert hasattr(app, "get_config_path")
    assert hasattr(app, "App")
    assert callable(app.resource_path)
    assert callable(app.get_config_path)
