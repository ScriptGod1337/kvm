#/bin/sh
cd $(dirname $(realpath "$0"))/..
./kvmutil.py 3 inputselect hdmi1
sleep 0.5
./kvmutil.py 3 pbp on
sleep 0.5
./kvmutil.py 3 pbpsubinputselect hdmi2
xrandr --output HDMI-1 --mode 2560x1440_55 --left-of HDMI-2
xrandr --output HDMI-2 --mode 2560x1440_55 --primary
