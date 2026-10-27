# Monitor

CO2 Monitor as Daemonset deployment

## Todo

Todo:
- collect data
- grafana dashboard

## Install

Configure the nodes with the config_hid.yaml playbook and apply the deployment.


## Manual steps for testing

Create the udev (/etc/udev/rules.d/50-local-raw-usb-co2monitor.rules) rule.

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="a052",  MODE="0666", GROUP="plugdev", TAG+="uaccess", SYMLINK+="comonitor"
```


Reload udev and check the comonitor symlink

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
ls -l /dev/comonitor
/dev/comonitor -> hidraw0
```


Build and push the image into harbor

```bash
podman build -t comonitor:v0.0.1 --platform linux/amd64,linux/arm64  --manifest manifest-comonitor:v0.0.1 .
podman login harbor.maus.local
podman manifest push manifest-comonitor:v0.0.1 harbor.maus.local/library/comonitor:v0.0.1
```


Local test, pass the device into the container.

```bash
podman run --rm -it --device /dev/comonitor:/dev/comonitor comonitor:v0.0.1
```
