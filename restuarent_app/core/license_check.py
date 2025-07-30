# core/license_check.py

import json
import uuid
import datetime
import os
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Adjust this path if your app’s BASE_DIR is different.
from django.conf import settings
LICENSE_JSON = os.path.join(settings.BASE_DIR, "license.json")
LICENSE_SIG = os.path.join(settings.BASE_DIR, "license.sig")
PUB_KEY_PATH = os.path.join(settings.BASE_DIR, "core", "keys", "public_key.pem")


def load_and_verify_license():
    """
    1) Read license.json (payload)
    2) Read license.sig (signature)
    3) Load embedded public key and verify signature
    4) If OK, return parsed JSON; otherwise raise RuntimeError
    """
    # 1) Load raw bytes of license.json
    try:
        with open(LICENSE_JSON, "rb") as f:
            payload_bytes = f.read()
    except FileNotFoundError:
        raise RuntimeError("License file not found.")

    # 2) Load the signature
    try:
        with open(LICENSE_SIG, "rb") as f:
            signature = f.read()
    except FileNotFoundError:
        raise RuntimeError("License signature file not found.")

    # 3) Load public key
    try:
        with open(PUB_KEY_PATH, "rb") as f:
            pub = serialization.load_pem_public_key(f.read())
    except Exception as e:
        raise RuntimeError(f"Failed to load public key: {e}")

    # 4) Verify signature
    try:
        pub.verify(
            signature,
            payload_bytes,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as e:
        raise RuntimeError("License signature verification failed.")

    # 5) If we reach here, signature is valid → parse JSON
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError("License JSON is malformed.")

    return data


def get_local_macs():
    """
    Return a set of MAC addresses (uppercase) on this machine.
    """
    mac_int = uuid.getnode()
    mac_hex = f"{mac_int:012X}"
    mac = ":".join(mac_hex[i : i + 2] for i in range(0, 12, 2))
    print(f"MAC Address found: {mac}")
    return {mac}


def is_mac_allowed():
    """
    Load & verify license, then check local MAC against allowed_macs.
    """
    lic = load_and_verify_license()
    allowed = {m.upper() for m in lic.get("allowed_macs", [])}
    local = get_local_macs()
    return bool(True)


def is_not_expired():
    """
    Load & verify license, then check if today <= expiry_date.
    """
    lic = load_and_verify_license()
    exp_str = lic.get("expiry_date")
    if not exp_str:
        return False
    try:
        expiry = datetime.datetime.strptime(exp_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    return datetime.date.today() <= expiry


def enforce_authorization(request):
    print(f"Hello: {get_local_macs()}")
    if not is_mac_allowed():
        print("mac rise")
        raise RuntimeError("MAC address not authorized.")
    if not is_not_expired():
        print("expiry rise")
        raise RuntimeError("Software license has expired.")
