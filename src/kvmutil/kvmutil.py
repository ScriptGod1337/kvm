#!/usr/bin/python3
import platform
from enum import Enum, auto
import argparse
import time

def isOSWin():
	return platform.system().lower() == "windows"
def isOsLinux():
	return platform.system().lower().startswith("linux")

if isOSWin(): from monitorcontrol import get_monitors
elif isOsLinux():
	from ddcci.ddcci import DDCCIDevice
	import subprocess
	import re
else: raise Exception("Unsupported OS '%s'" % platform.system())

# Defintion of DDC/CI codes
# ======================================================================================================================
class VCPCode(Enum):
	# see VESA Monitor Control Command Set Standard v2.21, page 81 - (e.g. https://milek7.pl/ddcbacklight/mccs.pdf)
	InputSelect					= 0x60

	# DELL (U4919DW?) specific
	DELL_U4919DW_PBP_SwapVideo	= 0xe5
	DELL_U4919DW_PBP_SwapInput	= 0xe7
	DELL_U4919DW_PBP_SubInput	= 0xe8
	DELL_U4919DW_PBP_Mode		= 0xe9
	UNKNOWN						= 0x00

class InputName(Enum):
	HDMI1				= auto()
	HDMI2				= auto()
	DisplayPort1		= auto()
	USBC_DELL_U4919DW	= auto()

class PBPCmd(Enum):
	ON	= auto()
	OFF	= auto()
	SWAP= auto()

VCPCodeValues = {
	VCPCode.InputSelect: {
		# see VESA Monitor Control Command Set Standard v2.21, page 81 - (e.g. https://milek7.pl/ddcbacklight/mccs.pdf)
		InputName.HDMI1:				0x11,
		InputName.HDMI2:				0x12,
		InputName.DisplayPort1:			0x0f,

		# DELL (U4919DW?) specific
		InputName.USBC_DELL_U4919DW:	0x1B1B,
	},
	VCPCode.DELL_U4919DW_PBP_SwapVideo: {
		PBPCmd.SWAP:					0xf000,
	},
	VCPCode.DELL_U4919DW_PBP_SwapInput: {
		PBPCmd.SWAP:					0xff00,
	},
	VCPCode.DELL_U4919DW_PBP_SubInput: {
		InputName.HDMI1:				0x11,
		InputName.HDMI2:				0x12,
		InputName.DisplayPort1:			0x0f,
		InputName.USBC_DELL_U4919DW:	0x1b,
	},
	VCPCode.DELL_U4919DW_PBP_Mode: {
		PBPCmd.ON:						0x24,
		PBPCmd.OFF:						0x00,
	}
}
# ======================================================================================================================

# Defintion of commands for cmdline
# ======================================================================================================================
class VCPCommand:
	def __init__(self, help, helpOptions, nargs, options: dict):
		self.help = help
		self.helpOptions = helpOptions
		self.options = options
		self.nargs = nargs

class VCPWriteCommand:
	def __init__(self, code: VCPCode, value: int):
		self.code = code
		self.value = value

	def __repr__(self):
		return "VCPWriteCommand(code=0x%02x value=0x%04x)" % (self.code.value, self.value)

vcpWriteCmds = {
	"InputSelect": VCPCommand(
		"Change input source selection",
		"Input source to switch to", 
		None, {
			InputName.HDMI1.name.lower(): 			VCPWriteCommand(VCPCode.InputSelect, VCPCodeValues[VCPCode.InputSelect][InputName.HDMI1]),
			InputName.HDMI2.name.lower(): 			VCPWriteCommand(VCPCode.InputSelect, VCPCodeValues[VCPCode.InputSelect][InputName.HDMI2]),
			InputName.DisplayPort1.name.lower():	VCPWriteCommand(VCPCode.InputSelect, VCPCodeValues[VCPCode.InputSelect][InputName.DisplayPort1]),

			# DELL U4919DW specific
			InputName.USBC_DELL_U4919DW.name.lower():VCPWriteCommand(VCPCode.InputSelect, VCPCodeValues[VCPCode.InputSelect][InputName.USBC_DELL_U4919DW]),
		},
	),
	"PBP": VCPCommand(
		"Change PBP mode options",
		"PBP command",
		"+", {
			"on":		VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_Mode, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_Mode][PBPCmd.ON]),
			"off":		VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_Mode, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_Mode][PBPCmd.OFF]),
			"swapvideo":VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SwapVideo, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SwapVideo][PBPCmd.SWAP]),
			"swapinput":VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SwapInput, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SwapInput][PBPCmd.SWAP]),
		},
	),
	"PBPSubInputSelect": VCPCommand(
		"Change the input source of the PBP sub picture",
		"Input source to switch to",
		None, {
			InputName.HDMI1.name.lower(): 			VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SubInput, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SubInput][InputName.HDMI1]),
			InputName.HDMI2.name.lower(): 			VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SubInput, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SubInput][InputName.HDMI2]),
			InputName.DisplayPort1.name.lower():	VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SubInput, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SubInput][InputName.DisplayPort1]),
			
			# DELL U4919DW specific
			InputName.USBC_DELL_U4919DW.name.lower():VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SubInput, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SubInput][InputName.USBC_DELL_U4919DW]),
		}
	),
}
# ======================================================================================================================
def parseDeviceID(deviceID: str):
	from friendlyname import findMonitorIndexByFriendlyName
	
	# if number use it directly
	if deviceID.isnumeric():
		try: return int(deviceID)
		except ValueError: raise Exception("If deviceID is a number it must be an int")

	# Only supports Windows
	if not isOSWin(): raise Exception("Display friendly name only supported on Windows")

	index = findMonitorIndexByFriendlyName(deviceID)
	if index is None: raise Exception("Display with friendly name '%s' not found" % deviceID)
	print("Found display name '%s' at ID=%d" % (deviceID, index))
	
	return index
# ======================================================================================================================
def openDevice(deviceID: int):
	print("Accessing device with ID=%i..." % deviceID)
	if isOSWin():
		device = get_monitors()[deviceID]
		device.open()
	elif isOsLinux():
		device = DDCCIDevice(deviceID)
	else: raise Exception("Unsupported OS '%s'" % platform.system())

	device.deviceID = deviceID
	return device

def readVCPValue(device, code: VCPCode):
	print("Reading VPCCode=0x%02x..." % code.value)
	if isOSWin():
		readValue = device.vcp.get_vcp_feature(code.value)[0]
	elif isOsLinux():
		# device.read() seems not to work -> use external ddcutil
		cmdOutput = str(subprocess.check_output(["ddcutil",
			"-b", str(device.deviceID),
			"getvcp", "0x%02x" % code.value]))

		match = re.match(".*sh=0x(\w{2}).*sl=0x(\w{2})", cmdOutput)
		if match == None: raise Exception("invalid output from ddcutil '%s'" % cmdOutput)

		readValue = int(match.group(1), 16) << 8 | int(match.group(2), 16)
		print("...ddcutil getvcp 0x%04x" % readValue)

	print("...got 0x%04x" % readValue)
	return readValue

def writeVCPValue(device, vcpWriteCmd: VCPWriteCommand):
	print("Sending %s..." % vcpWriteCmd)
	if isOSWin(): device.vcp.set_vcp_feature(vcpWriteCmd.code.value, vcpWriteCmd.value)
	elif isOsLinux(): device.write(vcpWriteCmd.code.value, vcpWriteCmd.value)
	else: raise Exception()

def executeVCPCmd(device, cmdName, parameter):
	vcpWriteCmd = vcpWriteCmds[cmdName].options[parameter]
	print("Executing the command %s=%s..." % (cmdName, parameter))

	writeVCPValue(device, vcpWriteCmd)

	print("...done")

def switchPBP(device):
	currentPBPValue = readVCPValue(device, VCPCode.DELL_U4919DW_PBP_Mode)
	if currentPBPValue == VCPCodeValues[VCPCode.DELL_U4919DW_PBP_Mode][PBPCmd.ON]: pbpMode = PBPCmd.ON
	elif currentPBPValue == VCPCodeValues[VCPCode.DELL_U4919DW_PBP_Mode][PBPCmd.OFF]: pbpMode = PBPCmd.OFF
	else: raise Exception("Unknown PBPMode %s" % currentPBPValue)
	print("Current PBPMode=%s" % pbpMode)

	if pbpMode == PBPCmd.OFF:
		print("Switching PBP on...")
		writeVCPValue(device, VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_Mode, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_Mode][PBPCmd.ON]))
		return PBPCmd.ON
	elif pbpMode == PBPCmd.ON:
		print("Switching PBP off...")
		writeVCPValue(device, VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_Mode, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_Mode][PBPCmd.OFF]))
		return PBPCmd.OFF

def switchPBPWithSub(device, subInputSource):
	if switchPBP(device) == PBPCmd.ON:
		print("PBP is on -> setting sub input...")
		
		if isOSWin():
			time.sleep(3.5)
			# Re-open display
			device = openDevice(device.deviceID)
		elif isOsLinux(): time.sleep(3)

		executeVCPCmd(device, "PBPSubInputSelect", subInputSource)
	else: print("PBP is off -> skip setting sub input")

def swapPBP(device):
	writeVCPValue(device, 
		VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SwapVideo, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SwapVideo][PBPCmd.SWAP]))
	
	time.sleep(0.5)
	
	writeVCPValue(device,
		VCPWriteCommand(VCPCode.DELL_U4919DW_PBP_SwapInput, VCPCodeValues[VCPCode.DELL_U4919DW_PBP_SwapInput][PBPCmd.SWAP]))

if __name__ == "__main__":
	argParser = argparse.ArgumentParser()
	argParser.add_argument("device", help="i2c bus ID of the device (Linux: e.g. determined via 'ddccontrol -p' || Windows: index in global display list or display friendly name)")
	# ---
	subParsers = argParser.add_subparsers(help="command categorie")
	for cmdName, cmdInfo in vcpWriteCmds.items():
		subParser = subParsers.add_parser(cmdName.lower(), help=cmdInfo.help)
		subParser.add_argument(cmdName, help=cmdInfo.helpOptions, choices=cmdInfo.options.keys(), nargs=cmdInfo.nargs)
	# ===
	subParser = subParsers.add_parser("pbpswitch", help="LOGIC: Switches PBP mode on/off")
	subParser.set_defaults(pbpswitch='do')
	# -
	subParser = subParsers.add_parser("pbpswitch2", help="LOGIC: Switches PBP mode on/off + selects input of the sub picture")
	subParser.add_argument("pbpswitch2", help="Input source to set sub input to", choices=vcpWriteCmds["PBPSubInputSelect"].options.keys())
	# -
	subParser = subParsers.add_parser("pbpswap", help="LOGIC: Swaps PBP video input source + USB input remains at the same video input")
	subParser.set_defaults(pbpswap='do')
	# ===
	args = argParser.parse_args()

	# open device
	deviceID = parseDeviceID(args.device)
	deviceObj = openDevice(deviceID)
	
	cmdExecuted = False

	# get commands & parameters
	for cmdName in vcpWriteCmds.keys():
		if hasattr(args, cmdName):
			selectedParams = getattr(args, cmdName)
			if isinstance(selectedParams, list):
				# multiple parameter
				cmdExecuted = True
				for selectedParam in selectedParams: executeVCPCmd(deviceObj, cmdName, selectedParam)
			elif not selectedParams is None:
				cmdExecuted = True
				executeVCPCmd(deviceObj, cmdName, selectedParams) # on parameter
	
	# PBP switch/wap
	if hasattr(args, "pbpswitch"):
		switchPBP(deviceObj)
		cmdExecuted = True
	elif hasattr(args, "pbpswitch2"):
		switchPBPWithSub(deviceObj, args.pbpswitch2)
		cmdExecuted = True
	elif hasattr(args, "pbpswap"):
		swapPBP(deviceObj)
		cmdExecuted = True

	if not cmdExecuted:
		# no commands selected
		argParser.print_usage()
		exit(1)
