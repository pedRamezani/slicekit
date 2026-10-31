import numpy as np
import pytest
from conftest import make_phantom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from slicekit.imaging import find_series, load_series, series_info


def write_series(folder, hu, spacing=(2.5, 0.8, 0.6), corner=(-30.0, -40.0, 100.0), suffix=".dcm", description="AXIAL"):
    """Write ``hu[z, y, x]`` as one CT file per slice, stored with intercept -1024."""
    dz, dy, dx = spacing
    folder.mkdir(parents=True, exist_ok=True)
    series_uid = generate_uid()
    for k, image in enumerate(hu):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = meta
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.Modality = "CT"
        ds.BodyPartExamined = "CHEST"
        ds.SeriesDescription = description
        ds.SeriesInstanceUID = series_uid
        ds.Rows, ds.Columns = image.shape
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
        ds.PixelSpacing = [dy, dx]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [corner[0], corner[1], corner[2] + k * dz]
        ds.RescaleIntercept, ds.RescaleSlope = -1024, 1
        ds.PixelData = (image.astype(np.int32) + 1024).astype(np.uint16).tobytes()
        # Reverse file names so loading has to sort by position.
        ds.save_as(folder / f"{description.lower()}_{len(hu) - k:03d}{suffix}", enforce_file_format=True)
    (folder / "notes.txt").write_text("not a dicom file")
    return series_uid


def test_load_series_roundtrip(tmp_path):
    hu = make_phantom(shape=(12, 30, 40)).hu
    write_series(tmp_path, hu)
    vol = load_series(tmp_path)
    np.testing.assert_array_equal(vol.hu, hu)
    assert vol.spacing == pytest.approx((2.5, 0.8, 0.6))
    assert vol.origin == pytest.approx((100.0, -40.0, -30.0))


def test_missing_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_series(tmp_path)


def test_series_without_extension_in_subfolder(tmp_path):
    """DICOM files are found by content, in subfolders, with or without a .dcm suffix."""
    hu = make_phantom(shape=(6, 20, 24)).hu
    uid = write_series(tmp_path / "export" / "SE0001", hu, suffix="")

    (info,) = series_info(tmp_path)  # recursive, like load_series
    assert (info.uid, info.images, info.modality, info.body_part) == (uid, 6, "CT", "CHEST")
    assert info.summary() == "CT | CHEST | 6 images | 20x24 | AXIAL"

    (found,) = find_series([tmp_path])
    assert found.folder == (tmp_path / "export" / "SE0001").resolve()
    np.testing.assert_array_equal(load_series(tmp_path).hu, hu)


def test_several_series_in_one_folder(tmp_path):
    big = write_series(tmp_path, make_phantom(shape=(8, 20, 24)).hu, description="BIG")
    small = write_series(tmp_path, make_phantom(shape=(4, 20, 24)).hu, corner=(0.0, 0.0, 0.0), description="SMALL")

    infos = series_info(tmp_path)
    assert [i.uid for i in infos] == [big, small]  # largest first, as load_series picks
    assert {i.uid for i in find_series([tmp_path, tmp_path])} == {big, small}  # each reported once
    assert load_series(tmp_path).hu.shape[0] == 8
    assert load_series(tmp_path, small).hu.shape[0] == 4
