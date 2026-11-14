"""Read the active Wi-Fi name through the operating system, without scanning."""
import platform


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
                adapter = str(profile.network_adapter.network_adapter_id).strip("{}").lower()
                name = ""
                try:
                    details = profile.wlan_connection_profile_details
                    if details is not None:
                        name = details.get_connected_ssid() or ""
                except OSError:
                    pass
                networks[adapter] = name
            return networks
        if system == "Darwin":
            from CoreWLAN import CWWiFiClient

            return {interface.interfaceName().lower(): interface.ssid() or ""
                    for interface in CWWiFiClient.sharedWiFiClient().interfaces() or ()
                    if interface.interfaceName()}
    except (ImportError, OSError, RuntimeError):
        pass
    return {}
