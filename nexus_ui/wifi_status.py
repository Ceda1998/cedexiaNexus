"""Read the active Wi-Fi name through the operating system, without scanning."""
import ctypes
import platform


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


def connected_wifi():
    """Map system interface IDs to active WLAN names (empty if withheld)."""
    system = platform.system()
    try:
        if system == "Windows":
            # WinRT uses these projections for the returned profile collection.
            import winrt.windows.foundation.collections
            from winrt.windows.networking.connectivity import NetworkConnectivityLevel, NetworkInformation

            networks = {}
            for profile in NetworkInformation.get_connection_profiles():
                if (not profile.is_wlan_connection_profile or profile.network_adapter is None
                        or profile.get_network_connectivity_level() == NetworkConnectivityLevel.NONE):
                    continue
                adapter = profile.network_adapter.network_adapter_id
                name = ""
                try:
                    details = profile.wlan_connection_profile_details
                    if details is not None:
                        name = details.get_connected_ssid() or ""
                except OSError:
                    pass
                networks[str(adapter).lower()] = name
                if interface_name := windows_interface_name(adapter):
                    networks[interface_name] = name
            return networks
        if system == "Darwin":
            from CoreWLAN import CWWiFiClient

            return {interface.interfaceName().lower(): interface.ssid() or ""
                    for interface in CWWiFiClient.sharedWiFiClient().interfaces() or ()
                    if interface.interfaceName()}
    except (ImportError, OSError, RuntimeError):
        pass
    return {}
