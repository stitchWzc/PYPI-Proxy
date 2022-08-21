# PYPI-Proxy
This is a proxy server for PYPI that is the repair version of https://github.com/tzulberti/Flask-PyPi-Proxy.git.

## What did we do
1. The verification algorithm was changed from MD5 to SHA256 to suit the current needs.(by thuhak)
2. Compatible python3.(by thuhak)
3. The User-agent header of the Web request is changed to circumvent the detection of the mirror site.(by thuhak)
4. Fixed timeout interruption when the client installs large installation packages through the proxy server by modifying the proxy server transmission mode.(by stitch)
5. Solve the problem that multiple processes write to cache files at the same time during concurrency.(by stitch)

## How to run
1. First, install the environment the program needs.You need to execute the following command：
```bash
pip install -r requirements.txt
```
2. Add pypi-proxy.service to /usr/lib/systemd/system/ .
3. Add a configuration file(pypi_proxy) to etc/sysconfig/,and Configure the following:
```bash
PYPI_PROXY_BASE_FOLDER_PATH="/data/pypi/simple"
PYPI_PROXY_LOGGING_PATH="/var/log/pypi/proxy.logs"
PYPI_PROXY_PYPI_URL="https://mirrors.aliyun.com/pypi"
PYPI_PROXY_LOGGING_LEVEL="ERROR"
```
4. Run the following to start the proxy service：
```bash
systemctl start pypi-proxy.service
```
5. Enjoy it all.