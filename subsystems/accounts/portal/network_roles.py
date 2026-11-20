"""What each network port may do. Pure Python, so it can be tested without Django.

Every port has one role:
- Off: the port is not used.
- Internet: the port is the Pi's connection to a router. At most one port can be Internet.
- Local: the port serves devices directly. Only Ethernet can be Local; Wi-Fi never serves devices (owner decision, todo 1.12).

Nothing here touches the Pi's network. Saving a pair of roles only records the choice.
"""
OFF = 'off'
INTERNET = 'internet'
LOCAL = 'local'
ROLES = (OFF, INTERNET, LOCAL)
DEFAULT_ETHERNET = OFF
DEFAULT_WIFI = INTERNET


def validate(ethernet, wifi):
    """Return why this pair of roles cannot be saved, or None when it can."""
    if ethernet not in ROLES or wifi not in ROLES:
        return 'Choose Off, Internet or Local for each port.'
    if ethernet == INTERNET and wifi == INTERNET:
        return 'Only one port can connect to the internet.'
    if ethernet == OFF and wifi == OFF:
        return 'Turn on at least one port, or the Pi cannot be reached.'
    if wifi == LOCAL:
        return 'Wi-Fi cannot serve devices directly. Direct mode is cable only.'
    return None
