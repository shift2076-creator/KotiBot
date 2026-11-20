import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from portal import site_settings_file
from portal.network_roles import DEFAULT_ETHERNET, DEFAULT_WIFI, ROLES


class User(AbstractUser):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80)
    role = models.CharField(max_length=5, choices=[('admin', 'Admin'), ('user', 'User')])
    service_access = models.JSONField(default=dict)
    vault_user_id = models.CharField(max_length=64, blank=True)
    vault_items = models.JSONField(default=dict)


class Invitation(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=80)
    role = models.CharField(max_length=5)
    services = models.JSONField(default=dict)
    created_by = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True)
    # Shared logins sealed in the admin's browser with a key that only the QR fragment carries. The server cannot open it.
    shared_sealed = models.TextField(blank=True, default='')


class Attempt(models.Model):
    scope = models.CharField(max_length=64, db_index=True)
    at = models.DateTimeField(db_index=True)


class Notification(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    source = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=64)
    level = models.CharField(max_length=8, choices=[('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')])
    title = models.CharField(max_length=200)
    message = models.TextField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=8, default='open', choices=[('open', 'Open'), ('resolved', 'Resolved')], db_index=True)
    resolution = models.CharField(max_length=16, blank=True)
    resolved_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='notification_resolutions')
    resolved_at = models.DateTimeField(null=True)


class NotificationReceipt(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='receipts')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['notification', 'user'], name='notification_seen_per_admin')]


class ClientRelease(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    client = models.CharField(max_length=16)
    version = models.CharField(max_length=64)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField()
    url = models.URLField(max_length=2048)
    release_url = models.URLField(max_length=2048)
    discovered_at = models.DateTimeField(auto_now_add=True)
    notification = models.OneToOneField(Notification, null=True, on_delete=models.PROTECT)


class SiteSettings(models.Model):
    """One row of Admin-controlled switches for the whole PiVault."""
    offline_mode = models.BooleanField(default=False)
    ethernet_role = models.CharField(max_length=8, default=DEFAULT_ETHERNET, choices=[(r, r.title()) for r in ROLES])
    wifi_role = models.CharField(max_length=8, default=DEFAULT_WIFI, choices=[(r, r.title()) for r in ROLES])

    @classmethod
    def is_offline(cls):
        if site_settings_file.path():
            return bool(site_settings_file.read().get('offline_mode', False))
        return bool(cls.objects.filter(pk=1).values_list('offline_mode', flat=True).first())

    @classmethod
    def set_offline(cls, value):
        if site_settings_file.path():
            site_settings_file.write({'offline_mode': bool(value)})
            return
        cls.objects.update_or_create(pk=1, defaults={'offline_mode': bool(value)})

    @classmethod
    def network_roles(cls):
        if site_settings_file.path():
            stored = site_settings_file.read()
            ethernet, wifi = stored.get('ethernet_role'), stored.get('wifi_role')
            if ethernet in ROLES and wifi in ROLES:
                return ethernet, wifi
            return DEFAULT_ETHERNET, DEFAULT_WIFI
        row = cls.objects.filter(pk=1).values('ethernet_role', 'wifi_role').first()
        if row is None:
            return DEFAULT_ETHERNET, DEFAULT_WIFI
        return row['ethernet_role'], row['wifi_role']

    @classmethod
    def set_network_roles(cls, ethernet, wifi):
        if site_settings_file.path():
            site_settings_file.write({'ethernet_role': ethernet, 'wifi_role': wifi})
            return
        cls.objects.update_or_create(pk=1, defaults={'ethernet_role': ethernet, 'wifi_role': wifi})


class ClientPackage(models.Model):
    client = models.CharField(max_length=16, primary_key=True)
    current = models.ForeignKey(ClientRelease, null=True, on_delete=models.PROTECT, related_name='+')
    previous = models.ForeignKey(ClientRelease, null=True, on_delete=models.PROTECT, related_name='+')
    latest = models.ForeignKey(ClientRelease, null=True, on_delete=models.PROTECT, related_name='+')
    checked_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=200, blank=True)


class Device(models.Model):
    """An Android phone, identified by a keyed hash of its ANDROID_ID rather than its serial number."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    identity = models.CharField(max_length=64, unique=True)
    model = models.CharField(max_length=80, blank=True)
    android_release = models.CharField(max_length=16, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True)


class DeviceApp(models.Model):
    """Desired package state (enabled or disabled) and last observed state of one app on one device."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='apps')
    client = models.CharField(max_length=16)
    enabled = models.BooleanField(default=True)
    observed_state = models.CharField(max_length=16, default='unknown')
    observed_version = models.CharField(max_length=64, blank=True)
    observed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['device', 'client'], name='one_app_state_per_device')]
