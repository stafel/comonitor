# Proposed replacement for the current Containerfile: gcr.io/distroless/python3 (Debian 13 / trixie).
#
# Build (same multi-arch workflow as before):
#   podman build -f Containerfile.distroless \
#     -t comonitor:distroless --platform linux/amd64,linux/arm64 \
#     --manifest manifest-comonitor:distroless .
#
# The distroless python3-debian13 image ships Python 3.13 (glibc 2.41) and has no
# shell, no pip and no package manager, so every install/build step happens in
# the builder stage and only the resulting Python tree is copied to the runtime.

ARG PYTHON_VERSION=3.13

# ---------- builder ---------------------------------------------------------
# Same distro (trixie) and Python minor version as the runtime image: hidapi is
# compiled from source into a cp313 extension linked against glibc 2.41, so a
# mismatched builder base yields an extension the runtime cannot import.
FROM --platform=$TARGETPLATFORM python:${PYTHON_VERSION}-slim-trixie AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential/pkg-config/libudev-dev compile the hidraw backend of hidapi.
# libudev1/libcap2 are that backend's *runtime* shared objects and are copied
# into the final stage below; the compiler toolchain never leaves this stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config libudev-dev libudev1 libcap2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY app/requirements.txt ./requirements.txt

# Dependencies go to /vendor, which PYTHONPATH points at in the runtime stage.
# HIDAPI_WITH_HIDRAW=1 + --no-binary=hidapi is load-bearing: the prebuilt
# manylinux wheel's `hid` module is the libusb backend (enumerate() returns
# bus/port paths such as b"9-1.4:1.0"), so open_path(b"/dev/comonitor") can
# never succeed. The source build yields the hidraw backend, which returns
# /dev/hidrawN paths and opens the node by name - what main.py relies on.
RUN HIDAPI_WITH_HIDRAW=1 pip install --target /vendor \
        --no-binary=hidapi -r requirements.txt

# Collect the hidraw backend's runtime .so dependencies. The multiarch triplet
# directory differs per architecture (/usr/lib/x86_64-linux-gnu on amd64,
# /usr/lib/aarch64-linux-gnu on arm64), so glob it instead of hardcoding one.
RUN mkdir -p /runtime-libs \
    && cp -a /usr/lib/*-linux-gnu/libudev.so.1* /usr/lib/*-linux-gnu/libcap.so.2* /runtime-libs/

# ---------- runtime ---------------------------------------------------------
FROM gcr.io/distroless/python3-debian13:nonroot

# main.py reads rooms.ini through a relative path, so the workdir matters.
WORKDIR /app

# The image entrypoint is /usr/bin/python3.13, hence only CMD can be overridden.
ENV PYTHONPATH=/vendor \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The source-built hid extension links libudev.so.1, which in turn links
# libcap.so.2; distroless ships neither. /usr/lib is on ld.so's default search
# path for both architectures, so no LD_LIBRARY_PATH/RPATH plumbing is required.
COPY --from=build /runtime-libs/ /usr/lib/

COPY --from=build /vendor /vendor
COPY app/main.py ./main.py

# Runs as nonroot (uid 65532); the udev rule grants 0666 on /dev/comonitor, so
# no privileges or capabilities are needed to open the hidraw node.
CMD ["/app/main.py"]
