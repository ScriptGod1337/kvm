
# KVM utilities (DELL)
Utility to work with the integrated hardware KVM switch of modern monitors.
> *Currently the focus of this tool is the DELL U4919DW*

## Components
The tool consists of two components
1. KVM Util: python based tool to send commands to the KVM switch and control it
2. MonitorTool Hook: reverse engineering tool for Windows closed source tools of the monitor manufacturers. It allows to spy on them to gather the VCP commands they write and read on the display

## KVM Util
### Prerequisites
>  Installed Python 3 of course.
#### a) Windows
 - installed external python package *monitorcontrol*  *(see to https://monitorcontrol.readthedocs.io/en/latest/ & https://github.com/newAM/monitorcontrol)*:
`pip3 install monitorcontrol`

 #### b) Linux
 - External git repository cloned into `kvm\ddcci`
 - Installed Python package *python-smbus*  `pip3 install smbus`
 - Installed ddcutil for `pbpswitch` commands (see https://www.ddcutil.com)
 `sudo apt-get install ddcutil`
 - User must have access to the i2c devices `/dev/i2c-X`: e.g. add user to group i2c

### Usage
>  First determine the device ID of the display. You can use `ddccontrol -p` on Linux. On Windows it's the 0-based index of the attached monitors.

**Get the *src* folder**, navigate to *src\kvmutil* and execute kvmutil.py.
```
kvmutil.py [-h] deviceid {inputselect,pbp,pbpsubinputselect,pbpswitch,pbpswitch2,pbpswap} ...
```
#### Usage examples
In the sub folders of `kvmutil` there are some examples of real usages of the tool in Windows (`kvmutil\win`) and Linux (`kvmutil\linux`) 

## MonitorTool Hook
The tool is written in C# and uses the EasyHook framework *(see https://easyhook.github.io/)*.

You can download the latest/nightly build: https://raw.githubusercontent.com/ScriptGod1337/kvm/master/downloads/MonitorToolHook.7z  
Usage: `Monitor.exe MonitorToolToSpy`  
For example for DELL `Monitor.exe "C:\Program Files (x86)\Dell\Dell Display Manager\ddm.exe"`

The monitor logs the VCP commands send by the program to the console. You can execute a functionality of the monitor manufacture tool and find out which VCP command with which parameter was written or read
```
Monitor.exe "C:\Program Files (x86)\Dell\Dell Display Manager\ddm.exe"
...
**read  OK GetVCPFeatureAndVCPFeatureReply_Hook 0x0 0xE5 0x0 0xFF
**read  OK GetVCPFeatureAndVCPFeatureReply_Hook 0x0 0xE7 0xFF20 0xFFAA
**read  OK GetVCPFeatureAndVCPFeatureReply_Hook 0x0 0xE8 0x12 0xFFFF
**read  OK GetVCPFeatureAndVCPFeatureReply_Hook 0x0 0xE9 0x0 0xFF
...
**write SetcVCPFeature 0x0 0xE9 0x24
...
```

***These values can be used in the KVM Util or in custom scripts***