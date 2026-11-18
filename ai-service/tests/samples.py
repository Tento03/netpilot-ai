"""Redacted sample outputs. SYNTHETIC = hand-made for cases not yet seen on the real network."""

PING_OK = """\

Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=19ms TTL=115
Reply from 8.8.8.8: bytes=32 time=20ms TTL=115
Reply from 8.8.8.8: bytes=32 time=23ms TTL=115

Ping statistics for 8.8.8.8:
    Packets: Sent = 3, Received = 3, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 19ms, Maximum = 23ms, Average = 20ms
"""

PING_VARIABLE = """\

Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=43ms TTL=115
Reply from 8.8.8.8: bytes=32 time=153ms TTL=115

Ping statistics for 8.8.8.8:
    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 43ms, Maximum = 153ms, Average = 98ms
"""

PING_ALL_LOST = """\

Pinging 203.0.113.1 with 32 bytes of data:
Request timed out.
Request timed out.

Ping statistics for 203.0.113.1:
    Packets: Sent = 2, Received = 0, Lost = 2 (100% loss),
"""

PING_NOHOST = "Ping request could not find host tidakada.invalid. Please check the name and try again.\n"

# SYNTHETIC
PING_SUB_MS = """\

Pinging 10.17.11.254 with 32 bytes of data:
Reply from 10.17.11.254: bytes=32 time<1ms TTL=255
Reply from 10.17.11.254: bytes=32 time=2ms TTL=255

Ping statistics for 10.17.11.254:
    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 0ms, Maximum = 2ms, Average = 1ms
"""

# SYNTHETIC: Windows counts these as "Received"
PING_UNREACHABLE = """\

Pinging 8.8.4.4 with 32 bytes of data:
Reply from 10.17.11.9: Destination host unreachable.
Reply from 10.17.11.9: Destination host unreachable.

Ping statistics for 8.8.4.4:
    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),
"""

NETSH_CONNECTED = """\

There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Test Wireless Adapter
    GUID                   : 00000000-0000-0000-0000-000000000000
    Physical address       : aa:bb:cc:dd:ee:01
    Interface type         : Primary
    State                  : connected
    SSID                   : OfficeWiFi
    AP BSSID               : aa:bb:cc:dd:ee:02
    Band                   : 5 GHz
    Channel                : 36
    Connected Akm-cipher   : [ akm = 00-0f-ac:02, cipher =  00-0f-ac:04 ]
    Network type           : Infrastructure
    Radio type             : 802.11ac
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto Connect
    Receive rate (Mbps)    : 780
    Transmit rate (Mbps)   : 780
    Signal                 : 81%
    Rssi                   : -67
    Profile                : OfficeWiFi
    QoS MSCS Configured         : 0
    QoS Map Configured          : 0
    QoS Map Allowed by Policy   : 0
"""

# SYNTHETIC
NETSH_DISCONNECTED = """\

There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Test Wireless Adapter
    State                  : disconnected
"""

# SYNTHETIC
NETSH_NO_SERVICE = "The Wireless AutoConfig Service (wlansvc) is not running.\n"

IPCONFIG = """\

Windows IP Configuration

   Host Name . . . . . . . . . . . . : TESTPC
   Primary Dns Suffix  . . . . . . . :
   Node Type . . . . . . . . . . . . : Hybrid
   IP Routing Enabled. . . . . . . . : No

Ethernet adapter Ethernet 2:

   Media State . . . . . . . . . . . : Media disconnected
   Connection-specific DNS Suffix  . :
   Description . . . . . . . . . . . : Fortinet Virtual Ethernet Adapter (NDIS 6.30)
   Physical Address. . . . . . . . . : 00-11-22-33-44-01
   DHCP Enabled. . . . . . . . . . . : Yes

Ethernet adapter Ethernet:

   Media State . . . . . . . . . . . : Media disconnected
   Connection-specific DNS Suffix  . :
   Description . . . . . . . . . . . : Realtek PCIe GbE Family Controller
   Physical Address. . . . . . . . . : 00-11-22-33-44-02
   DHCP Enabled. . . . . . . . . . . : Yes

Wireless LAN adapter Wi-Fi:

   Connection-specific DNS Suffix  . :
   Description . . . . . . . . . . . : Test Wireless Adapter
   Physical Address. . . . . . . . . : AA-BB-CC-DD-EE-01
   DHCP Enabled. . . . . . . . . . . : Yes
   Autoconfiguration Enabled . . . . : Yes
   Link-local IPv6 Address . . . . . : fe80::a1a3:155c:8925:b6f1%19(Preferred)
   IPv4 Address. . . . . . . . . . . : 10.17.11.9(Preferred)
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 10.17.11.254
   DHCP Server . . . . . . . . . . . : 10.17.11.254
   DNS Servers . . . . . . . . . . . : 118.98.115.69
                                       118.98.115.78
   NetBIOS over Tcpip. . . . . . . . : Enabled
"""