# Distroless image (proposal)

We want the runtime image to be `gcr.io/distroless/python3` (Debian 13) instead of
`python:3-slim`. `Containerfile.distroless` is the validated candidate; build it with:

```bash
podman build -f Containerfile.distroless \
  -t comonitor:distroless --platform linux/amd64,linux/arm64 \
  --manifest manifest-comonitor:distroless .
```

## Why a builder stage is mandatory

The distroless `python3` image has no shell, no `pip`, no `apt` and no compiler, so
everything is installed in a `python:3.13-slim-trixie` builder stage and only the
resulting Python tree (`/vendor`, on `PYTHONPATH`) is copied over.

Two constraints keep the extension loadable on both architectures:

* The builder must use **the same distro and Python minor version** as the runtime
  (`trixie`/3.13) - hidapi compiles to a `cp313` extension linked against glibc 2.41.
* `HIDAPI_WITH_HIDRAW=1` together with `--no-binary=hidapi` must be kept: the prebuilt
  manylinux wheel is the **libusb** backend, whose `enumerate()` returns bus/port paths
  (`b"9-1.4:1.0"`), so `open_path(b"/dev/comonitor")` cannot work. The source build is
  the **hidraw** backend (paths `b"/dev/hidrawN"`), which is what `main.py` needs.

## Runtime dependencies that distroless does not ship

The source-built `hid` extension links `libudev.so.1` (which links `libcap.so.2`).
Both are copied from the builder into `/usr/lib`, the one directory on ld.so's
default search path for amd64 and arm64 alike. Verified with `/proc/self/maps` on
both architectures: `/usr/lib/libudev.so.1.7.10` and `/usr/lib/libcap.so.2.75` are
loaded from there, and `hid.enumerate()` returns the same device list as on the
current image.

`configparser`, OTLP/HTTP and TLS need nothing extra; the image already sets
`SSL_CERT_FILE` and ships `ca-certificates`.

## Deployment changes

`deployment/dset.yaml` needs a new image tag and can be tightened, because opening a
hidraw node only needs read/write on the 0666 device created by the udev rule:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
# privileged: true is no longer required
```

The app never writes to disk (`PYTHONDONTWRITEBYTECODE=1` is set), so a read-only
root filesystem is fine. `rooms.ini` keeps being mounted at `/app/rooms.ini`; `/app`
exists in the image because of `WORKDIR`.

## Trade-offs and risks

* **Python downgrade**: `python:3-slim` currently resolves to 3.15.2, distroless
  Debian 13 ships 3.13.5. Nothing in `app/` or in `requirements.txt` needs 3.14+.
* **No shell**: `kubectl exec` only works with the `:debug` variant
  (`gcr.io/distroless/python3-debian13:debug`). Keep it documented for troubleshooting.
* **Emulated arm64 builds**: `--platform linux/amd64,linux/arm64` compiles hidapi under
  QEMU for arm64, which is slow. Native per-arch builders produce faster builds.
* **Size**: ~75 MB (amd64) / ~88 MB (arm64) versus ~490 MB today, and no apt/shell in
  the attack surface.
* Pin the base image by digest for reproducible builds; the `:nonroot` tag also sets
  uid 65532, which the udev rule's `MODE="0666"` already accommodates.
