import argparse
import subprocess
import unittest
from unittest.mock import patch

from clusterctl import install
from clusterctl.main import cmd_install


def inventory() -> dict:
    return {
        "hosts": {
            "new-host": {
                "org": {
                    "install": {
                        "enable": True,
                        "installationId": "new-host-root-disk",
                    }
                }
            }
        },
        "hostBootstrap": {
            "new-host": {
                "install": {
                    "enable": True,
                    "installationId": "new-host-root-disk",
                    "targetHost": "192.0.2.10",
                    "sshUser": "root",
                    "sshPort": 22,
                    "identityFile": None,
                    "expectedLiveHostName": "nbootstrap-live",
                    "expectedLiveMarker": "nbootstrap-live-v1",
                    "expectedHardware": {
                        "sysVendor": "Example",
                        "productName": "Safe Test Host",
                    },
                    "expectedDiskSize": {
                        "minimumBytes": 900000000,
                        "maximumBytes": 1100000000,
                    },
                    "disko": {
                        "devices": {
                            "disk": {
                                "system": {
                                    "device": "/dev/disk/by-id/test-root",
                                }
                            }
                        }
                    },
                }
            }
        },
    }


def safe_probe() -> dict[str, str]:
    return {
        "hostname": "nbootstrap-live",
        "os_id": "nixos",
        "root_source": "rootfs",
        "root_fstype": "tmpfs",
        "live_marker": "nbootstrap-live-v1",
        "sys_vendor": "Example",
        "product_name": "Safe Test Host",
        "disk_exists": "true",
        "disk_mounted": "false",
        "disk_size": "1000000000",
        "disk_model": "Test Disk",
    }


class InstallSafetyTests(unittest.TestCase):
    def test_requires_matching_double_opt_in(self):
        data = inventory()
        data["hosts"]["new-host"]["org"]["install"]["installationId"] = "wrong"
        with self.assertRaisesRegex(install.InstallError, "mismatched"):
            install.resolve_plan(data, "new-host")

    def test_refuses_installed_nixos(self):
        plan = install.resolve_plan(inventory(), "new-host")
        result = safe_probe()
        result["root_source"] = "/dev/mapper/system-root"
        result["root_fstype"] = "ext4"
        with self.assertRaisesRegex(install.InstallError, "installed NixOS"):
            install.validate_probe(plan, result)

    def test_refuses_wrong_hardware(self):
        plan = install.resolve_plan(inventory(), "new-host")
        result = safe_probe()
        result["product_name"] = "Important Production Host"
        with self.assertRaisesRegex(install.InstallError, "product_name"):
            install.validate_probe(plan, result)

    def test_refuses_wrong_disk_size(self):
        plan = install.resolve_plan(inventory(), "new-host")
        result = safe_probe()
        result["disk_size"] = "12000000000000"
        with self.assertRaisesRegex(install.InstallError, "outside expected range"):
            install.validate_probe(plan, result)

    def test_dry_run_never_invokes_nixos_anywhere(self):
        args = argparse.Namespace(
            flake=".",
            host="new-host",
            confirm=None,
            dry_run=True,
        )
        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory()),
            patch("clusterctl.main.install.probe", return_value=safe_probe()),
            patch("clusterctl.main.subprocess.run") as run,
        ):
            self.assertEqual(cmd_install(args), 0)
        run.assert_not_called()

    def test_install_requires_exact_confirmation(self):
        args = argparse.Namespace(
            flake=".",
            host="new-host",
            confirm="wrong",
            dry_run=False,
        )
        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory()),
            patch("clusterctl.main.install.probe", return_value=safe_probe()),
            patch("clusterctl.main.subprocess.run") as run,
        ):
            self.assertEqual(cmd_install(args), 2)
        run.assert_not_called()

    def test_install_runs_nixos_anywhere_after_all_checks(self):
        args = argparse.Namespace(
            flake=".",
            host="new-host",
            confirm="new-host-root-disk",
            dry_run=False,
        )
        completed = subprocess.CompletedProcess([], 0)
        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory()),
            patch("clusterctl.main.install.probe", return_value=safe_probe()),
            patch(
                "clusterctl.main.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            self.assertEqual(cmd_install(args), 0)
        run.assert_called_once_with(
            [
                "nixos-anywhere",
                "--flake",
                ".#new-host",
                "--target-host",
                "root@192.0.2.10",
                "--phases",
                "disko,install,reboot",
            ],
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
