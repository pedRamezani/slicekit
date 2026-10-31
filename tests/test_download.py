"""Offline tests: the IDC client is replaced by a fake with a tiny index."""

import pytest

pd = pytest.importorskip("pandas")

from slicekit.imaging import idc as download  # noqa: E402  (after the pandas skip)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.index = pd.DataFrame({
            "SeriesInstanceUID": ["axial", "coronal", "mr", "few", "nc", "big"],
            "collection_id": ["nlst", "nlst", "nlst", "nlst", "other", "nlst"],
            "BodyPartExamined": ["CHEST", "CHEST", "CHEST", "CHEST", "CHEST", "chest"],
            "SeriesDescription": ["1,STANDARD,2.5", "COR 3mm", "T1", "SCOUT", "Lung", "ax"],
            "Modality": ["CT", "CT", "MR", "CT", "CT", "CT"],
            "instanceCount": [120, 120, 120, 2, 120, 300],
            "series_size_MB": [10.0, 9.0, 5.0, 1.0, 8.0, 80.0],
            "license_short_name": ["CC BY 4.0"] * 4 + ["CC BY-NC 3.0", "CC BY 4.0"],
        })

    def get_series_size(self, uid):
        return 10.0

    def download_from_selection(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(download, "client", lambda: client)
    return client


def test_search_keeps_axial_ct_with_open_licence(fake):
    rows = download.find_ct_series(body_part="chest")
    assert list(rows.SeriesInstanceUID) == ["axial", "big"]


def test_search_filters(fake):
    assert list(download.find_ct_series(max_size_mb=50).SeriesInstanceUID) == ["axial"]
    assert list(download.find_ct_series(collection="OTHER", licenses=None).SeriesInstanceUID) == ["nc"]
    assert "coronal" in set(download.find_ct_series(axial_only=False).SeriesInstanceUID)


def test_download_series_layout(fake, tmp_path):
    path = download.download_series("axial", tmp_path)
    assert path == tmp_path / "axial"
    (call,) = fake.calls
    assert call["seriesInstanceUID"] == ["axial"]
    assert call["dirTemplate"] == "%SeriesInstanceUID"
    assert call["downloadDir"] == str(tmp_path)
