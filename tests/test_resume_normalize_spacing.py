import importlib
import queue
import threading
from types import SimpleNamespace


main = importlib.import_module("main")


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_worker_checkpoint_preserves_disabled_normalize_spacing_on_resume():
    results = queue.Queue()
    source = SimpleNamespace(translation_start_settings={"normalize_spacing": False})

    def collect_settings():
        try:
            results.put(main.App._settings_dict(source))
        except Exception as error:
            results.put(error)

    worker = threading.Thread(target=collect_settings, daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "worker settings collection did not finish"
    settings = results.get_nowait()
    if isinstance(settings, Exception):
        raise settings

    restored = SimpleNamespace(
        **{name: Value(value) for name, value in {
            "provider_var": "", "url_var": "", "model_var": "",
            "preset_var": "CK3", "batch_var": 40, "workers_var": 1,
            "repair_var": True, "dual_var": False, "autoqa_var": True,
            "glossary_path_var": "", "normalize_spacing_var": True,
            "progress_text": "",
        }.items()},
        _write_session_file=lambda **kwargs: None,
        _refresh_queue_tree=lambda: None,
        _save_workspace_state=lambda reason: None,
    )
    main.App.restore_session(restored, {"settings": settings, "queue": []})

    assert settings.get("normalize_spacing") is False
    assert restored.normalize_spacing_var.get() is False
