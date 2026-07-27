"""Resumen de lote con un fallo intermedio (C2), sin red ni descargas reales."""

from pathlib import Path

from tae.online import runner as runner_mod
from tae.online.errors import DownloadFailed, FailureCause
from tae.online.models import (
    OnlineJobOptions,
    OnlineJobResult,
    PlaylistEntry,
    UrlInfo,
)


def _entries(n):
    return [
        PlaylistEntry(url=f"http://v{i}", title=f"Video {i}", video_id=f"v{i}", index=i)
        for i in range(1, n + 1)
    ]


def test_run_playlist_captura_fallo_y_sigue(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner_mod, "probe_url",
        lambda url: UrlInfo(is_playlist=True, entries=_entries(3), playlist_title="Lista"),
    )

    seen_stems = []

    def fake_run_url(opts, *, out_stem=None, **kw):
        seen_stems.append(out_stem)
        if opts.url == "http://v2":
            raise DownloadFailed(
                "es privado", cause=FailureCause.PRIVATE, url=opts.url
            )
        return OnlineJobResult(title=f"ok-{opts.url}", txt_path=Path("x.txt"))

    monkeypatch.setattr(runner_mod, "run_url", fake_run_url)

    opts = OnlineJobOptions(url="http://list", out_dir=tmp_path)
    report = runner_mod.run_playlist(opts)

    assert report.total == 3
    assert len(report.successes) == 2
    assert len(report.failures) == 1
    assert report.failures[0].cause is FailureCause.PRIVATE
    assert report.failures[0].title == "Video 2"
    # numeracion NN_ aplicada en orden
    assert seen_stems == ["01_Video 1", "02_Video 2", "03_Video 3"]


def test_run_playlist_error_inesperado_no_tumba_lote(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner_mod, "probe_url",
        lambda url: UrlInfo(is_playlist=True, entries=_entries(2)),
    )

    def fake_run_url(opts, *, out_stem=None, **kw):
        if opts.url == "http://v1":
            raise RuntimeError("algo raro")
        return OnlineJobResult(title="ok")

    monkeypatch.setattr(runner_mod, "run_url", fake_run_url)

    report = runner_mod.run_playlist(OnlineJobOptions(url="http://list", out_dir=tmp_path))
    assert len(report.successes) == 1
    assert len(report.failures) == 1
    assert report.failures[0].cause is FailureCause.UNKNOWN


def test_summarize_batch_texto_legible(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner_mod, "probe_url",
        lambda url: UrlInfo(is_playlist=True, entries=_entries(2)),
    )

    def fake_run_url(opts, *, out_stem=None, **kw):
        if opts.url == "http://v2":
            raise DownloadFailed("x", cause=FailureCause.GEOBLOCKED, url=opts.url)
        return OnlineJobResult(title="ok")

    monkeypatch.setattr(runner_mod, "run_url", fake_run_url)
    report = runner_mod.run_playlist(OnlineJobOptions(url="http://list", out_dir=tmp_path))
    texto = runner_mod.summarize_batch(report)
    assert "1 ok" in texto
    assert "1 con fallo" in texto
    assert "Video 2" in texto
