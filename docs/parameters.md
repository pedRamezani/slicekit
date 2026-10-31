# Parameters

Every setting of `slicekit`, as a `KitParams` field, a `slicekit` command-line flag
and an entry in the interactive menu's parameter editor. All lengths are **printed
millimetres**, so they apply after `scale`.

This table is generated from the field definitions in `slicekit.pipeline.params` each time
the documentation is built, so it always matches the installed version.

```python exec="on"
from slicekit.cli.options import parameter_table

print(parameter_table())
```

`hu_range` and `normals` take two values, e.g. `--hu-range -900 400` or
`--normals z x`. Yes/no settings have a `--no-` form, e.g. `--no-perceptual`.
In Python, pass the same names to `KitParams`:

```python
from slicekit import KitParams, make_kit

kit = make_kit("path/to/dicom_folder", KitParams(scale=0.4, infill="lines", pitch=4.0))
```
