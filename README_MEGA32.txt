MEGA32 - Runtime Builder native Linux dependencies

Base incremental: MEGA31 + MEGA31A.

Fixes:
- Installs GEOS development libraries required by Shapely 1.8.0.
- Adds GDAL, Cairo, JPEG, PNG and TIFF development libraries for common vision/custom-node builds.
- Validates geos-config and libgeos_c.so during Docker build.
- Preserves Python 3.11, pip 25, CUDA 12.8, PyTorch cu128, Transformers <5 and custom-node protections.

After applying, export a NEW runtime context. Do not rebuild an older exported Dockerfile.
