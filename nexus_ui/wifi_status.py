"""Read the active Wi-Fi name through the operating system, without scanning."""
import ctypes
import platform
from uuid import UUID


def windows_interface_name(adapter_id):
    # Qt uses the interface name from NET_LUID and falls back to the GUID.
    ip_helper = ctypes.WinDLL("iphlpapi.dll")
    guid_to_luid = ip_helper.ConvertInterfaceGuidToLuid
    guid_to_luid.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64))
    guid_to_luid.restype = ctypes.c_uint32
    luid_to_name = ip_helper.ConvertInterfaceLuidToNameW
    luid_to_name.argtypes = (ctypes.POINTER(ctypes.c_uint64), ctypes.c_wchar_p, ctypes.c_size_t)
    luid_to_name.restype = ctypes.c_uint32
    guid = ctypes.create_string_buffer(adapter_id.bytes_le, 16)
    luid = ctypes.c_uint64()
    name = ctypes.create_unicode_buffer(257)
    if guid_to_luid(guid, ctypes.byref(luid)) == 0 and luid_to_name(ctypes.byref(luid), name, len(name)) == 0:
        return name.value.lower()
    return ""


def windows_wlan_adapters():
    """Enumerate connected WLAN interfaces without reading location data."""
    class InterfaceInfo(ctypes.Structure):
        _fields_ = (("guid", ctypes.c_ubyte * 16), ("description", ctypes.c_uint16 * 256),
                    ("state", ctypes.c_uint32))

    api = ctypes.WinDLL("wlanapi.dll")
    handle, version, result = ctypes.c_void_p(), ctypes.c_uint32(), ctypes.c_void_p()
    api.WlanOpenHandle.argtypes = (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    api.WlanEnumInterfaces.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    api.WlanFreeMemory.argtypes = (ctypes.c_void_p,)
    api.WlanFreeMemory.restype = None
    api.WlanCloseHandle.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
        return []
    try:
        if api.WlanEnumInterfaces(handle, None, ctypes.byref(result)) or result.value is None:
            return []
        count = ctypes.c_uint32.from_address(result.value).value
        entries = (InterfaceInfo * count).from_address(result.value + 8)
        return [UUID(bytes_le=bytes(entry.guid)) for entry in entries if entry.state in (1, 2)]
    finally:
        if result.value is not None:
            api.WlanFreeMemory(result)
        api.WlanCloseHandle(handle, None)


def windows_wifi():
    networks = {}
    try:
        networks.update(dict.fromkeys(windows_wlan_adapters(), ""))
    except OSError:
        pass
    try:
        # WinRT uses this projection for the collection of profiles.
        import winrt.windows.foundation.collections
        from winrt.windows.networking.connectivity import NetworkConnectivityLevel, NetworkInformation

        try:
            profiles = list(NetworkInformation.get_connection_profiles())
        except OSError:
            profiles = []
        if preferred := NetworkInformation.get_internet_connection_profile():
            profiles.append(preferred)
        for profile in profiles:
            if (not profile.is_wlan_connection_profile or profile.network_adapter is None
                    or profile.get_network_connectivity_level() == NetworkConnectivityLevel.NONE):
                continue
            adapter = profile.network_adapter.network_adapter_id
            networks.setdefault(adapter, "")
            try:
                details = profile.wlan_connection_profile_details
                if details is not None and (name := details.get_connected_ssid()):
                    networks[adapter] = name
            except (OSError, RuntimeError):
                pass
    except (ImportError, OSError, RuntimeError):
        pass
    result = {str(adapter): name for adapter, name in networks.items()}
    for adapter, name in networks.items():
        if interface_name := windows_interface_name(adapter):
            result[interface_name] = name
    return result


def connected_wifi():
    """Map system interface IDs to active WLAN names (empty if withheld)."""
    system = platform.system()
    try:
        if system == "Windows":
            return windows_wifi()
        if system == "Darwin":
            from CoreWLAN import CWWiFiClient

            return {interface.interfaceName().lower(): interface.ssid() or ""
                    for interface in CWWiFiClient.sharedWiFiClient().interfaces() or ()
                    if interface.interfaceName()}
    except (ImportError, OSError, RuntimeError):
        pass
    return {}
