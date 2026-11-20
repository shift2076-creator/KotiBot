"""Turn a pair of port roles into NetworkManager commands, and decide when a change must revert.

Pure Python: it builds lists of commands and files and runs nothing, so it can be tested anywhere.
The root-owned host helper (not written yet) will run the commands. Nothing here touches the Pi.

Role names mirror subsystems/accounts/portal/network_roles.py. Owner decisions (todo 1.12, 2026-11-19):
- One identity address, 192.168.4.90, in every mode.
- Local clients get no internet by default.
- Direct mode is cable only: Wi-Fi never serves clients (no access point).
- Local subnet 10.42.0.0/24, the Pi at 10.42.0.1.
Spike findings (claude/network-spike-20261119.md) shape the steps below.
"""
from collections import namedtuple

OFF, INTERNET, LOCAL = 'off', 'internet', 'local'
ROLES = (OFF, INTERNET, LOCAL)

IDENTITY_ADDRESS = '192.168.4.90'
LOCAL_SUBNET = '10.42.0.0/24'
LOCAL_GATEWAY = '10.42.0.1/24'
ETHERNET = 'eth0'
WIFI = 'wlan0'
IDENTITY_INTERFACE = 'kb-id0'
PROFILE_IDENTITY = 'kotibot-identity'
PROFILE_UPLINK = 'kotibot-eth-uplink'
PROFILE_LOCAL = 'kotibot-eth-local'
SHARED_DNSMASQ_FILE = '/etc/NetworkManager/dnsmasq-shared.d/kotibot-local.conf'
# NetworkManager's shared DHCP only: its own DNS is off (pivault-dns keeps port 53) and clients are told to use pivault-dns.
SHARED_DNSMASQ_CONTENT = 'port=0\ndhcp-option=6,' + IDENTITY_ADDRESS + '\n'
GRACE_SECONDS = 120

# argv: the command as a list (never a shell string). tolerate: a failure is fine, for example deleting a profile that is not there.
Step = namedtuple('Step', 'argv tolerate')
# up: bring the new setup up first. down: remove the old one only after the helper has checked that the new one works.
# files: path -> content, or None to remove the file.
Plan = namedtuple('Plan', 'error up down firewall files')


def _nm(*argv, tolerate=False):
    return Step(('nmcli',) + argv, tolerate)


def _drop_between(a, b):
    """Refuse forwarded traffic from interface a to interface b (idempotent: delete, then insert)."""
    rule = ('DOCKER-USER', '-i', a, '-o', b, '-j', 'DROP')
    return [Step(('iptables', '-D') + rule, True), Step(('iptables', '-I') + rule, False)]


def unsupported(ethernet, wifi):
    """Why this pair cannot be applied, or None. Wi-Fi never serves clients; the Pi must stay reachable."""
    if ethernet not in ROLES or wifi not in ROLES:
        return 'Choose Off, Internet or Local for each port.'
    if ethernet == INTERNET and wifi == INTERNET:
        return 'Only one port can connect to the internet.'
    if ethernet == OFF and wifi == OFF:
        return 'Turn on at least one port, or the Pi cannot be reached.'
    if wifi == LOCAL:
        return 'Wi-Fi cannot serve devices directly yet. Direct mode is cable only.'
    return None


def identity_steps():
    """A dummy interface that holds the identity address, so Docker and pivault-dns can bind without Wi-Fi."""
    return [
        _nm('connection', 'delete', 'id', PROFILE_IDENTITY, tolerate=True),
        _nm('connection', 'add', 'type', 'dummy', 'ifname', IDENTITY_INTERFACE, 'con-name', PROFILE_IDENTITY,
            'ipv4.method', 'manual', 'ipv4.addresses', IDENTITY_ADDRESS + '/32', 'ipv6.method', 'disabled',
            'connection.autoconnect', 'yes'),
        _nm('connection', 'up', 'id', PROFILE_IDENTITY),
    ]


def plan(ethernet, wifi, *, identity=False, wired_profile='Wired connection 1', wifi_profile='Room 237'):
    """Commands for one pair of roles. Check .error first; when it is set the other fields are empty."""
    reason = unsupported(ethernet, wifi)
    if reason:
        return Plan(reason, [], [], [], {})
    up, down, firewall, files = [], [], [], {}
    if identity:
        up += identity_steps()
    # Always stop the stock auto-DHCP profile: a cable must never quietly become the default route.
    stock_off = _nm('connection', 'modify', 'id', wired_profile, 'connection.autoconnect', 'no', tolerate=True)
    wifi_on = _nm('connection', 'modify', 'id', wifi_profile, 'connection.autoconnect', 'yes')
    wifi_off = [_nm('connection', 'modify', 'id', wifi_profile, 'connection.autoconnect', 'no'),
                _nm('device', 'disconnect', WIFI, tolerate=True)]
    if ethernet == INTERNET:
        up += [stock_off,
               _nm('connection', 'delete', 'id', PROFILE_LOCAL, tolerate=True),
               _nm('connection', 'delete', 'id', PROFILE_UPLINK, tolerate=True),
               _nm('connection', 'add', 'type', 'ethernet', 'ifname', ETHERNET, 'con-name', PROFILE_UPLINK,
                   'ipv4.method', 'auto', 'ipv6.method', 'auto', 'connection.autoconnect', 'yes'),
               _nm('connection', 'up', 'id', PROFILE_UPLINK)]
        files[SHARED_DNSMASQ_FILE] = None
        down += wifi_off  # Wi-Fi is Off here: the other pairs are refused above.
    elif ethernet == LOCAL:
        up += [stock_off,
               _nm('connection', 'delete', 'id', PROFILE_UPLINK, tolerate=True),
               _nm('connection', 'delete', 'id', PROFILE_LOCAL, tolerate=True),
               _nm('connection', 'add', 'type', 'ethernet', 'ifname', ETHERNET, 'con-name', PROFILE_LOCAL,
                   'ipv4.method', 'shared', 'ipv4.addresses', LOCAL_GATEWAY, 'ipv6.method', 'disabled',
                   'connection.autoconnect', 'yes'),
               _nm('connection', 'up', 'id', PROFILE_LOCAL)]
        files[SHARED_DNSMASQ_FILE] = SHARED_DNSMASQ_CONTENT
        if wifi == INTERNET:
            up.append(wifi_on)
            # NetworkManager's shared method adds its own NAT and forward rules; these drops keep Local clients off the internet.
            firewall += _drop_between(ETHERNET, WIFI) + _drop_between(WIFI, ETHERNET)
        else:
            down += wifi_off
    else:  # Ethernet off; Wi-Fi is the Internet port (todays network).
        up.append(wifi_on)
        down += [stock_off,
                 _nm('connection', 'delete', 'id', PROFILE_UPLINK, tolerate=True),
                 _nm('connection', 'delete', 'id', PROFILE_LOCAL, tolerate=True),
                 _nm('device', 'disconnect', ETHERNET, tolerate=True)]
        files[SHARED_DNSMASQ_FILE] = None
    return Plan(None, up, down, firewall, files)


# Confirm-or-revert. A role change can cut the admin's own session, so the helper applies it, waits for a confirmation,
# and goes back to the last good roles if none arrives in time.

def begin_change(previous, requested, now, grace=GRACE_SECONDS):
    """State to store while a change waits for confirmation. previous and requested are (ethernet, wifi) pairs."""
    return {'previous': list(previous), 'requested': list(requested), 'deadline': now + grace, 'confirmed': False}


def confirm(change):
    return dict(change, confirmed=True)


def must_revert(change, now):
    """True when the change was never confirmed and its time is up."""
    return not change['confirmed'] and now >= change['deadline']


def revert_target(change):
    return tuple(change['previous'])
