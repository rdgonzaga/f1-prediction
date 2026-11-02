"""Windows toast notifications for the hidden scheduled runner."""
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable

APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$t = [Security.SecurityElement]::Escape($env:F1PRED_TOAST_TITLE)
$b = [Security.SecurityElement]::Escape($env:F1PRED_TOAST_BODY)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>")
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:F1PRED_TOAST_APP).Show(
    [Windows.UI.Notifications.ToastNotification]::new($xml))
"""
MAX_BODY = 200


def toast(title: str, body: str, run: Callable[..., object] = subprocess.run) -> None:
    """Best effort: a missing or broken notifier never fails the run."""
    if sys.platform != "win32":
        return
    env = os.environ | {"F1PRED_TOAST_TITLE": title, "F1PRED_TOAST_BODY": body[:MAX_BODY],
                        "F1PRED_TOAST_APP": APP_ID}
    try:
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SCRIPT], env=env, timeout=30,
            capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        print(f"Toast failed: {exc}")
