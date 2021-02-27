from monitorcontrol import get_monitors

import ctypes
from ctypes.wintypes import (
	BOOL, USHORT, UINT, DWORD, ULONG, LONG, LARGE_INTEGER,
	WCHAR,
	POINTL, RECT, HMONITOR,
)

# createGDIName2FriendlyName
#==============================================================
QDC_ALL_PATHS								= 1
QDC_ONLY_ACTIVE_PATHS 						= 2
DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE			= 1
DISPLAYCONFIG_MODE_INFO_TYPE_TARGET 		= 2
DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME	= 1
DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME	= 2
# --- generic
# ---------------------------
class LUID(ctypes.Structure):
	_fields_ = [
		('LowPart', DWORD),
		('HighPart', LONG),
	]
class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
	_fields_ = [
		('Numerator', UINT),
		('Denominator', UINT),
	]
class DISPLAYCONFIG_2DREGION(ctypes.Structure):
	_fields_ = [
		('cx', UINT),
		('cz', UINT),
	]
# --- DISPLAYCONFIG_PATH_INFO
# ---------------------------
class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
	_fields_ = [
		('adapterId', LUID),
		('id', UINT),
		('modeInfoIdx', UINT),
		('statusFlags', UINT),
	]
class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
	_fields_ = [
		('adapterId', LUID),
		('id', UINT),
		('modeInfoIdx', UINT),
		('outputTechnology', UINT),
		('rotation', UINT),
		('scaling', UINT),
		('refreshRate', DISPLAYCONFIG_RATIONAL),
		('scanLineOrdering', UINT),
		('targetAvailable', BOOL),
		('statusFlags', UINT),
	]
class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
	_fields_ = [
		("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
		("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
		('statusFlags', UINT),
	]
# --- DISPLAYCONFIG_MODE_INFO
# ---------------------------
class DISPLAYCONFIG_VIDEO_SIGNAL_INFO(ctypes.Structure):
	_fields_ = [
		("pixelRate", LARGE_INTEGER),
		("hSyncFreq", DISPLAYCONFIG_RATIONAL),
		("vSyncFreq", DISPLAYCONFIG_RATIONAL),
		("activeSize", DISPLAYCONFIG_2DREGION),
		("totalSize", DISPLAYCONFIG_2DREGION),
		("videoStandard", UINT), # union with AdditionalSignalInfo ignored
		("scanLineOrdering", UINT),
	]
class DISPLAYCONFIG_SOURCE_MODE(ctypes.Structure):
	_fields_ = [
		("width", UINT),
		("height", UINT),
		("pixelFormat", UINT),
		("position", POINTL),
	]
class DISPLAYCONFIG_MODE_INFO_DUMMYUNIONNAME(ctypes.Union):
	_fields_ = [
		("target", DISPLAYCONFIG_VIDEO_SIGNAL_INFO),
		("sourceMode", DISPLAYCONFIG_SOURCE_MODE),
		# desktopImageInfo if union ignored
	]
class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
	_fields_ = [
		("infoType", UINT),
		("id", UINT),
		("adapterId", LUID),
		("mode", DISPLAYCONFIG_MODE_INFO_DUMMYUNIONNAME),
	]
# ------------------------
class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
	_fields_ = [
		("type", UINT),
		("size", UINT),
		("adapterId", LUID),
		("id", UINT),
	]

class DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
	_fields_ = [
		("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
		("viewGDIName", WCHAR * 32),
	]

class DISPLAYCONFIG_TARGET_DEVICE_NAME(ctypes.Structure):
	_fields_ = [
		("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
		("flags", UINT),
		("outputTechnology", UINT),
		("edidManufactureId", USHORT),
		("edidProductCodeId", USHORT),
		("connectorInstance", UINT),
		("monitorFriendlyDeviceName", WCHAR * 64),
		("monitorDevicePath", WCHAR * 128),
	]
# ------------------------
# reads \\.\DISPLAYx for an adapter
def getGDINameFromSource(adapterId: LUID, sourceId: UINT):
	request = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
	
	request.header.size = ctypes.sizeof(DISPLAYCONFIG_SOURCE_DEVICE_NAME)
	request.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
	request.header.adapterId = adapterId
	request.header.id = sourceId
	winAPIResult = ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(request))
	if winAPIResult != 0: raise Exception("DisplayConfigGetDeviceInfo failed %d" % winAPIResult)

	return request.viewGDIName

# readsDisplayFriendlyName for an adapter
def getFriendlyNameFromTarget(adapterId: LUID, sourceId: UINT):
	request = DISPLAYCONFIG_TARGET_DEVICE_NAME()

	request.header.size = ctypes.sizeof(DISPLAYCONFIG_TARGET_DEVICE_NAME)
	request.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME
	request.header.adapterId = adapterId
	request.header.id = sourceId
	winAPIResult = ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(request))
	if winAPIResult != 0: raise Exception("DisplayConfigGetDeviceInfo failed %d" % winAPIResult)

	return request.monitorFriendlyDeviceName

# queries all known display information for all adapters
def readDisplayModes():
	countPathElements = DWORD()
	countModeElements = DWORD()

	# get buffer necessary and allocated
	winAPIResult = ctypes.windll.user32.GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(countPathElements), ctypes.byref(countModeElements))
	if winAPIResult != 0: raise Exception("GetDisplayConfigBufferSizes failed %d" % winAPIResult)
	displayPaths = (DISPLAYCONFIG_PATH_INFO * countPathElements.value)()
	displayModes = (DISPLAYCONFIG_MODE_INFO * countModeElements.value)()

	# query data
	winAPIResult = ctypes.windll.user32.QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS,
		ctypes.byref(countPathElements), displayPaths,
		ctypes.byref(countModeElements), displayModes,
		0)
	if winAPIResult != 0: raise Exception("QueryDisplayConfig failed %d" % winAPIResult)

	return [displayModes[n] for n in range(0, countModeElements.value)]

# creates map \\.\DISPLAYx to DisplyFreindlyName
def createGDIName2FriendlyName():
	displayModes = readDisplayModes()

	adapterKeys = set()
	adapterKey2GDIName = dict()
	adapterKey2FriendlyName = dict()
	for mode in displayModes:
		adapterKey = "%d-%d" % (mode.adapterId.LowPart, mode.adapterId.HighPart)
		adapterKeys.add(adapterKey)

		if mode.infoType == DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE:
			GDIName = getGDINameFromSource(mode.adapterId, mode.id)
			adapterKey2GDIName[adapterKey] = GDIName
		elif mode.infoType == DISPLAYCONFIG_MODE_INFO_TYPE_TARGET:
			friendlyName = getFriendlyNameFromTarget(mode.adapterId, mode.id)
			adapterKey2FriendlyName[adapterKey] = friendlyName
		else: raise Exception("Invalid infoType %d" % mode.infoType)

	gdiName2FriendlyName = dict()
	for adapterKey in adapterKeys:
		friendlyName = adapterKey2FriendlyName[adapterKey]
		gdiName = adapterKey2GDIName[adapterKey]

		gdiName2FriendlyName[gdiName] = friendlyName
	
	return gdiName2FriendlyName

# findMonitorIndexByFriendlyName
#==============================================================
class MONITORINFOEXW(ctypes.Structure):
	_fields_ = [
		("cbSize", ULONG),
		("rcMonitor", RECT),
		("rcWork", RECT),
		("dwFlags", ULONG),
		("szDevice", WCHAR * 32),
	]

# reads \\.\DISPLAYx for monitor ID for HMONITOR
def readGDIName(hmonitor: HMONITOR):
	monitorinfo = MONITORINFOEXW()
	monitorinfo.cbSize = ctypes.sizeof(MONITORINFOEXW)
	winAPIResult = ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(monitorinfo))
	if winAPIResult != 1: raise Exception("GetMonitorInfoW failed %d" % winAPIResult)

	return monitorinfo.szDevice

def createGDIName2MonitorIndex():
	gdiName2MonitorResult = dict()

	monitors = get_monitors()
	for n in range(0, monitors.count):
		hmonitor = monitors[n].vcp.hmonitor
		gdiName = readGDIName(hmonitor)
		gdiName2MonitorResult[n] = gdiName
	
	return gdiName2MonitorResult

def findMonitorIndexByFriendlyName(friendlyName: str):
	gdiName2FriendlyName = createGDIName2FriendlyName()

	monitors = get_monitors()
	for n in range(0, len(monitors)):
		hmonitor = monitors[n].vcp.hmonitor
		gdiName = readGDIName(hmonitor)

		currentFriendlyName = gdiName2FriendlyName[gdiName]
		if friendlyName.casefold() == currentFriendlyName.casefold(): return n
	
	return None