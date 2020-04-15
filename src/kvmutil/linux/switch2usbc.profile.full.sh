#/bin/sh
cd $(dirname $(realpath "$0"))/..
./kvmutil.py 3 inputselect usbc_dell_4919dw
sleep 1
./kvmutil.py 3 pbp off
