import argparse
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clusterctl import deploy as deploy_mod
from clusterctl.main import (
    build_parser,
    build_identity_matrix,
    cmd_deploy,
    cmd_identity_matrix,
    cmd_identity_generate_missing,
    cmd_identity_publish,
    cmd_identity_rotate,
    cmd_registry_ensure_v1,
    flake_identity_records,
    identity_publish_requires_sudo,
    leader_user_for_host,
    live_identity_matrices_from_registry,
    publish_generated_identities,
    publish_identity_ledger_after_deploy,
    registry_already_has_identity,
    registry_needs_v1_reseed,
    signing_key_path,
    capture_onion_mirror_identity,
    capture_status_ipns_name,
)
from clusterctl.events import write_json
from clusterctl.execution import SudoAuthorization


class IdentityRequirementsTest(unittest.TestCase):
    def rotate_args(self, service="yggdrasil", publish=False):
        return argparse.Namespace(
            flake=".",
            registry=Path("/var/lib/cluster-identity/registry"),
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            node="node-a",
            service=service,
            generation=None,
            allow_missing=False,
            dry_run=False,
            sops_age_key_file=Path("/var/lib/cluster-identity/age/host.agekey"),
            publish=publish,
            publish_push=False,
            notify=False,
            no_reconcile=False,
            leader=None,
            leader_key=None,
            signing_key=None,
            signature=None,
            no_commit=False,
        )

    def publish_args(self):
        return argparse.Namespace(
            registry=Path("/var/lib/cluster-identity/registry"),
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            flake=".",
            service=["git-annex"],
            node=["t320-0"],
            generation=None,
            state=None,
            leader=None,
            leader_key=None,
            signature=None,
            signing_key=None,
            allow_duplicate=False,
            allow_cross_leader_publish=False,
            no_commit=False,
            no_reconcile=False,
            fetch=True,
            push=True,
            remote=[],
            notify=False,
        )

    def test_public_command_surface_excludes_retired_commands(self):
        parser = build_parser()
        top_level = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        registry = top_level.choices["registry"]
        registry_commands = next(
            action
            for action in registry._actions
            if isinstance(action, argparse._SubParsersAction)
        ).choices
        identity = top_level.choices["identity"]
        identity_commands = next(
            action
            for action in identity._actions
            if isinstance(action, argparse._SubParsersAction)
        ).choices
        bundle = top_level.choices["bundle"]
        bundle_commands = next(
            action
            for action in bundle._actions
            if isinstance(action, argparse._SubParsersAction)
        ).choices

        self.assertNotIn("vm", top_level.choices)
        self.assertTrue(
            {
                "init",
                "materialize",
                "sync",
                "push",
                "remotes",
                "resign-placeholders",
            }.isdisjoint(registry_commands)
        )
        self.assertTrue(
            {"publish-public", "publish-inventory", "status", "apply"}.isdisjoint(
                identity_commands
            )
        )
        self.assertNotIn("publish", bundle_commands)
        self.assertIn("emergency-publish", bundle_commands)
        self.assertIn("rotate", identity_commands)

    def test_matrix_uses_flake_requirement_surface(self):
        inventory = {
            "hosts": {
                "leader": {"dendrites": ["system/cluster-identity"]},
                "follower": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {
                "byHost": {
                    "leader": {
                        "ipns-publisher": {
                            "service": "ipns-publisher",
                            "generator": "ipns-publisher",
                            "sourceLedger": "inventory/identity-services/ipns-publisher.nix",
                        }
                    },
                    "follower": {},
                }
            },
            "identities": {
                "services": {
                    "ipns-publisher": {},
                }
            },
        }

        report = build_identity_matrix(inventory)

        self.assertEqual(report["services"], ["ipns-publisher"])
        self.assertEqual(report["missing"][0]["node"], "leader")
        self.assertEqual(
            report["missing"][0]["requirement"]["generator"],
            "ipns-publisher",
        )
        self.assertEqual(
            report["rows"][0]["nodes"]["follower"]["status"], "not-applicable"
        )

    def test_matrix_overlays_live_registry_state(self):
        inventory = {
            "hosts": {
                "leader": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {
                "byHost": {
                    "leader": {
                        "status-ipns": {
                            "service": "status-ipns",
                            "generator": "status-ipns",
                            "sourceLedger": "inventory/identity-services/status-ipns.nix",
                        }
                    },
                }
            },
            "identities": {
                "services": {
                    "status-ipns": {
                        "leader": {
                            "generation": 1,
                            "state": "active",
                            "sourceTimestamp": "2026-06-29T02:39:45Z",
                            "public": {"ipnsName": "k51-flake"},
                        }
                    }
                }
            },
        }

        report = build_identity_matrix(
            inventory,
            live_records={
                "leader": {
                    "status-ipns": [
                        {
                            "generation": 2,
                            "state": "staged",
                            "leader": "leader-a",
                        },
                        {
                            "generation": 3,
                            "state": "active",
                            "leader": "leader-b",
                        },
                    ]
                }
            },
        )

        cell = report["rows"][0]["nodes"]["leader"]
        self.assertEqual(cell["cell"], "g1/a")
        self.assertEqual(
            [record["generation"] for record in cell["liveRecord"]], [2, 3]
        )
        self.assertEqual(
            [
                (matrix["leader"], matrix["rows"][0]["nodes"]["leader"]["cell"])
                for matrix in report["liveMatrices"]
            ],
            [("leader-a", "g2/s"), ("leader-b", "g3/a")],
        )

    def test_live_matrices_use_accepted_events_for_each_leader(self):
        with tempfile.TemporaryDirectory() as root:
            registry = Path(root)
            write_json(
                registry / "events" / "r640-0" / "000000000001.json",
                {
                    "schema": "cluster.identity.event.v1",
                    "eventId": "r640-event",
                    "eventHash": "sha256:r640",
                    "payloadHash": "sha256:r640-payload",
                    "leader": "r640-0",
                    "subject": {"node": "node-a", "service": "status-ipns"},
                    "generation": 1,
                    "state": "active",
                },
            )
            write_json(
                registry / "events" / "t320-0" / "000000000001.json",
                {
                    "schema": "cluster.identity.event.v1",
                    "eventId": "t320-event",
                    "eventHash": "sha256:t320",
                    "payloadHash": "sha256:t320-payload",
                    "leader": "t320-0",
                    "subject": {"node": "node-a", "service": "status-ipns"},
                    "generation": 2,
                    "state": "staged",
                },
            )

            matrices = live_identity_matrices_from_registry(
                registry, ["node-a"], {"status-ipns"}
            )

        self.assertEqual(
            [
                (matrix["leader"], matrix["rows"][0]["nodes"]["node-a"]["cell"])
                for matrix in matrices
            ],
            [("r640-0", "g1/a"), ("t320-0", "g2/s")],
        )

    def test_matrix_fetches_live_registry_state_by_default(self):
        inventory = {
            "hosts": {
                "leader": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {"byHost": {"leader": {}}},
            "identities": {"services": {}},
        }
        args = argparse.Namespace(
            flake=".",
            service=[],
            node=[],
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            no_live=False,
            fetch=True,
            only_missing=False,
            json=True,
        )

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch(
                "clusterctl.main.fetch_live_identity_records",
                return_value={
                    "leader": {"status-ipns": [{"generation": 2, "state": "active"}]}
                },
            ) as fetch_live,
        ):
            result = cmd_identity_matrix(args)

        self.assertEqual(result, 0)
        fetch_live.assert_called_once_with(args.policy, args.out)

    def test_matrix_can_skip_fetching_live_registry_state(self):
        inventory = {
            "hosts": {
                "leader": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {"byHost": {"leader": {}}},
            "identities": {"services": {}},
        }
        args = argparse.Namespace(
            flake=".",
            service=[],
            node=[],
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            no_live=False,
            fetch=False,
            only_missing=False,
            json=True,
        )

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch("clusterctl.main.fetch_live_identity_records") as fetch_live,
            patch("clusterctl.main.live_identity_records", return_value={}) as live,
        ):
            result = cmd_identity_matrix(args)

        self.assertEqual(result, 0)
        fetch_live.assert_not_called()
        live.assert_called_once_with(args.out)

    def test_rotate_replaces_inventory_record_with_next_generation(self):
        inventory = {
            "hosts": {
                "node-a": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {
                "byHost": {
                    "node-a": {
                        "yggdrasil": {
                            "service": "yggdrasil",
                            "generator": "yggdrasil",
                            "sourceLedger": "inventory/identity-services/yggdrasil.nix",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "yggdrasil": {
                        "node-a": {
                            "generation": 2,
                            "state": "active",
                            "public": {
                                "yggdrasilAddress": "200::old",
                                "yggdrasilPublicKey": "old",
                            },
                        },
                    },
                },
            },
        }

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch(
                "clusterctl.main.capture_yggdrasil_public",
                return_value={"publicKey": "new", "address": "200::new"},
            ),
            patch("clusterctl.main.update_identity_source_file") as update_identity,
            patch("clusterctl.main.stage_flake_paths") as stage,
        ):
            result = cmd_identity_rotate(self.rotate_args())

        self.assertEqual(result, 0)
        update_identity.assert_called_once()
        self.assertEqual(
            update_identity.call_args.args[:3], (".", "yggdrasil", "node-a")
        )
        record = update_identity.call_args.args[3]
        self.assertEqual(record["generation"], 3)
        self.assertEqual(record["public"]["yggdrasilPublicKey"], "new")
        stage.assert_called_once()

    def test_rotate_uses_live_generation_when_flake_lags(self):
        inventory = {
            "hosts": {
                "node-a": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {
                "byHost": {
                    "node-a": {
                        "yggdrasil": {
                            "service": "yggdrasil",
                            "generator": "yggdrasil",
                            "sourceLedger": "inventory/identity-services/yggdrasil.nix",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "yggdrasil": {
                        "node-a": {
                            "generation": 2,
                            "state": "active",
                            "public": {
                                "yggdrasilAddress": "200::old",
                                "yggdrasilPublicKey": "old",
                            },
                        },
                    },
                },
            },
        }

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch("clusterctl.main.known_identity_generation", return_value=6),
            patch(
                "clusterctl.main.capture_yggdrasil_public",
                return_value={"publicKey": "new", "address": "200::new"},
            ),
            patch("clusterctl.main.update_identity_source_file") as update_identity,
            patch("clusterctl.main.stage_flake_paths"),
        ):
            result = cmd_identity_rotate(self.rotate_args())

        self.assertEqual(result, 0)
        record = update_identity.call_args.args[3]
        self.assertEqual(record["generation"], 7)

    def test_rotate_refuses_extra_ledger_identity(self):
        inventory = {
            "hosts": {
                "node-a": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {"byHost": {"node-a": {}}},
            "identities": {
                "services": {
                    "yggdrasil": {
                        "node-a": {
                            "generation": 2,
                            "state": "active",
                            "public": {
                                "yggdrasilAddress": "200::old",
                                "yggdrasilPublicKey": "old",
                            },
                        },
                    },
                },
            },
        }

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch("clusterctl.main.update_identity_source_file") as update_identity,
            patch("clusterctl.main.cmd_identity_burn") as burn,
        ):
            result = cmd_identity_rotate(self.rotate_args())

        self.assertEqual(result, 2)
        update_identity.assert_not_called()
        burn.assert_not_called()

    def test_rotate_host_age_updates_recipient_generation(self):
        inventory = {
            "hosts": {
                "node-a": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {
                "byHost": {
                    "node-a": {
                        "host-age": {
                            "service": "host-age",
                            "generator": "host-age",
                            "sourceLedger": "inventory/keys/host-age-recipients.nix",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "host-age": {
                        "node-a": {
                            "generation": 4,
                            "state": "active",
                            "public": {"ageRecipient": "age1old"},
                        },
                    },
                },
            },
        }

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch(
                "clusterctl.main.rotate_host_age_key",
                return_value=(
                    "age1new",
                    "/var/lib/cluster-identity/age/host.agekey.old",
                ),
            ),
            patch("clusterctl.main.update_host_age_recipient_file") as update_host_age,
            patch("clusterctl.main.stage_flake_paths") as stage,
        ):
            result = cmd_identity_rotate(self.rotate_args(service="host-age"))

        self.assertEqual(result, 0)
        update_host_age.assert_called_once_with(".", "node-a", "age1new", generation=5)
        stage.assert_called_once()

    def test_rotate_publishes_rotated_generation_when_enabled(self):
        inventory = {
            "hosts": {
                "node-a": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {
                "byHost": {
                    "node-a": {
                        "ssh-host": {
                            "service": "ssh-host",
                            "generator": "ssh-host",
                            "sourceLedger": "inventory/identity-services/ssh-host.nix",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "ssh-host": {
                        "node-a": {
                            "generation": 1,
                            "state": "active",
                            "public": {"sshHostKey": "ssh-ed25519 OLD"},
                        },
                    },
                },
            },
        }

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch(
                "clusterctl.main.capture_ssh_host_key",
                return_value="ssh-ed25519 NEW",
            ),
            patch("clusterctl.main.update_identity_source_file"),
            patch("clusterctl.main.stage_flake_paths"),
            patch(
                "clusterctl.main.publish_generated_identities", return_value=0
            ) as publish,
        ):
            result = cmd_identity_rotate(
                self.rotate_args(service="ssh-host", publish=True)
            )

        self.assertEqual(result, 0)
        publish.assert_called_once()
        publish_args = publish.call_args.args[0]
        self.assertEqual(publish_args.node, ["node-a"])
        self.assertEqual(publish_args.service, ["ssh-host"])
        self.assertEqual(publish_args.generation, 2)

    def test_rotate_rejects_reused_generation(self):
        inventory = {
            "hosts": {
                "node-a": {"dendrites": ["system/cluster-identity"]},
            },
            "identityRequirements": {
                "byHost": {
                    "node-a": {
                        "ssh-host": {
                            "service": "ssh-host",
                            "generator": "ssh-host",
                            "sourceLedger": "inventory/identity-services/ssh-host.nix",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "ssh-host": {
                        "node-a": {
                            "generation": 2,
                            "state": "active",
                            "public": {"sshHostKey": "ssh-ed25519 OLD"},
                        },
                    },
                },
            },
        }
        args = self.rotate_args(service="ssh-host")
        args.generation = 2

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch("clusterctl.main.update_identity_source_file") as update_identity,
        ):
            result = cmd_identity_rotate(args)

        self.assertEqual(result, 2)
        update_identity.assert_not_called()

    def test_non_registry_bootstrap_identity_is_not_published(self):
        inventory = {
            "identityRequirements": {
                "byHost": {
                    "leader": {
                        "ipns-publisher": {
                            "registryPublish": False,
                        }
                    }
                }
            },
            "identities": {
                "services": {
                    "ipns-publisher": {
                        "leader": {
                            "generation": 1,
                            "state": "active",
                            "public": {"ipnsName": "k51-test"},
                        }
                    }
                }
            },
        }

        self.assertEqual(list(flake_identity_records(inventory)), [])

    def test_generated_identity_publication_uses_scoped_sudo(self):
        completed = argparse.Namespace(returncode=0)
        with (
            patch("clusterctl.main.identity_publish_requires_sudo", return_value=True),
            patch(
                "clusterctl.execution.sudo_authorization_status",
                return_value=SudoAuthorization.CACHED,
            ),
            patch(
                "clusterctl.main.clusterctl_executable",
                return_value="/nix/store/clusterctl/bin/clusterctl",
            ),
            patch("clusterctl.main.subprocess.run", return_value=completed) as run,
        ):
            result = publish_generated_identities(self.publish_args())

        self.assertEqual(result, 0)
        run.assert_called_once_with(
            [
                "sudo",
                "--",
                "/nix/store/clusterctl/bin/clusterctl",
                "--flake",
                ".",
                "identity",
                "publish",
                "--registry",
                "/var/lib/cluster-identity/registry",
                "--out",
                "/run/cluster-identity",
                "--policy",
                "/etc/cluster-identity/policy.json",
                "--service",
                "git-annex",
                "--node",
                "t320-0",
                "--burn-stale",
                "--fetch",
                "--push",
            ],
            check=False,
        )

    def test_generated_identity_publication_preserves_cross_leader_publish_escape_hatch(
        self,
    ):
        args = self.publish_args()
        args.allow_cross_leader_publish = True
        completed = argparse.Namespace(returncode=0)
        with (
            patch("clusterctl.main.identity_publish_requires_sudo", return_value=True),
            patch(
                "clusterctl.execution.sudo_authorization_status",
                return_value=SudoAuthorization.CACHED,
            ),
            patch(
                "clusterctl.main.clusterctl_executable",
                return_value="/nix/store/clusterctl/bin/clusterctl",
            ),
            patch("clusterctl.main.subprocess.run", return_value=completed) as run,
        ):
            result = publish_generated_identities(args)

        self.assertEqual(result, 0)
        command = run.call_args.args[0]
        self.assertIn("--allow-cross-leader-publish", command)

    def test_deploy_stays_unprivileged_by_default(self):
        args = argparse.Namespace(
            flake=".",
            hosts=["r640-0"],
            out=Path("/run/cluster-identity"),
            dry_run=False,
            local_root=False,
        )
        completed = argparse.Namespace(returncode=0)
        with (
            patch(
                "clusterctl.main.transport.inventory",
                return_value={"hosts": {"r640-0": {}}},
            ),
            patch("clusterctl.main.resolve_hosts_arg", return_value=["r640-0"]),
            patch("clusterctl.main.os.geteuid", return_value=1000),
            patch("clusterctl.main.deploy.candidates", return_value=[]),
            patch("clusterctl.main.subprocess.run", return_value=completed) as run,
            patch("clusterctl.main.os.execvp") as execvp,
        ):
            result = cmd_deploy(args)

        self.assertEqual(result, 0)
        execvp.assert_not_called()
        run.assert_called_once()

    def test_successful_deploy_publishes_from_the_deploying_leader(self):
        args = argparse.Namespace(
            flake=".",
            hosts=["r640-0"],
            out=Path("/run/cluster-identity"),
            dry_run=False,
            local_root=False,
            publish_identities=True,
        )
        completed = subprocess.CompletedProcess([], 0)
        with (
            patch(
                "clusterctl.main.transport.inventory",
                return_value={"hosts": {"r640-0": {}}},
            ),
            patch("clusterctl.main.resolve_hosts_arg", return_value=["r640-0"]),
            patch("clusterctl.main.os.geteuid", return_value=1000),
            patch("clusterctl.main.deploy.candidates", return_value=[]),
            patch(
                "clusterctl.main.clusterctl_executable",
                return_value="/nix/store/clusterctl/bin/clusterctl",
            ),
            patch(
                "clusterctl.main.identity_publish_requires_sudo",
                return_value=True,
            ),
            patch(
                "clusterctl.execution.sudo_authorization_status",
                return_value=SudoAuthorization.CACHED,
            ),
            patch(
                "clusterctl.main.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            result = cmd_deploy(args)

        self.assertEqual(result, 0)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["nix", "run", ".#deploy-rs", "--", "--skip-checks", ".#r640-0"],
                [
                    "sudo",
                    "--",
                    "/nix/store/clusterctl/bin/clusterctl",
                    "--flake",
                    ".",
                    "identity",
                    "publish",
                    "--out",
                    "/run/cluster-identity",
                    "--no-fetch",
                    "--allow-cross-leader-publish",
                ],
            ],
        )

    def test_successful_deploy_keeps_accessible_identity_publish_unprivileged(self):
        args = argparse.Namespace(
            flake=".",
            out=Path("/run/cluster-identity"),
            dry_run=False,
            publish_identities=True,
        )
        completed = subprocess.CompletedProcess([], 0)
        with (
            patch(
                "clusterctl.main.identity_publish_requires_sudo",
                return_value=False,
            ),
            patch(
                "clusterctl.main.clusterctl_executable",
                return_value="/nix/store/clusterctl/bin/clusterctl",
            ),
            patch(
                "clusterctl.main.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            result = publish_identity_ledger_after_deploy(args)

        self.assertEqual(result, 0)
        self.assertEqual(
            run.call_args.args[0][0],
            "/nix/store/clusterctl/bin/clusterctl",
        )

    def test_deploy_all_routes_boot_unchanged_hosts_to_colmena(self):
        args = argparse.Namespace(
            flake=".",
            hosts=["all"],
            out=Path("/run/cluster-identity"),
            dry_run=False,
            local_root=False,
        )
        completed = subprocess.CompletedProcess(
            ["nix", "run", ".#colmena", "--", "apply", "switch"],
            0,
        )

        with (
            patch(
                "clusterctl.main.transport.inventory",
                return_value={"hosts": {"r640-0": {}}},
            ),
            patch(
                "clusterctl.main.deploy.boot_risk_reasons",
                return_value=[],
            ),
            patch("clusterctl.main.os.geteuid", return_value=1000),
            patch("clusterctl.main.subprocess.run", return_value=completed) as run,
        ):
            result = cmd_deploy(args)

        self.assertEqual(result, 0)
        run.assert_called_once_with(
            [
                "nix",
                "run",
                ".#colmena",
                "--",
                "apply",
                "switch",
                "--on",
                "r640-0",
            ],
            check=False,
        )

    def test_deploy_all_routes_boot_changes_to_deploy_rs_first(self):
        args = argparse.Namespace(
            flake=".",
            hosts=["all"],
            out=Path("/run/cluster-identity"),
            dry_run=False,
            local_root=False,
        )
        completed = subprocess.CompletedProcess([], 0)

        def risks(host, _flake):
            if host == "t320-0":
                return ["generated fstab changes"]
            return []

        with (
            patch(
                "clusterctl.main.transport.inventory",
                return_value={
                    "hosts": {
                        "r640-0": {},
                        "t320-0": {},
                    }
                },
            ),
            patch(
                "clusterctl.main.deploy.boot_risk_reasons",
                side_effect=risks,
            ),
            patch("clusterctl.main.os.geteuid", return_value=1000),
            patch(
                "clusterctl.main.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            result = cmd_deploy(args)

        self.assertEqual(result, 0)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["nix", "run", ".#deploy-rs", "--", "--skip-checks", ".#t320-0"],
                [
                    "nix",
                    "run",
                    ".#colmena",
                    "--",
                    "apply",
                    "switch",
                    "--on",
                    "r640-0",
                ],
            ],
        )

    def test_deploy_all_dry_run_does_not_invoke_guarded_host(self):
        args = argparse.Namespace(
            flake=".",
            hosts=["all"],
            out=Path("/run/cluster-identity"),
            dry_run=True,
            local_root=False,
        )
        with (
            patch(
                "clusterctl.main.transport.inventory",
                return_value={"hosts": {"t320-0": {}}},
            ),
            patch(
                "clusterctl.main.deploy.boot_risk_reasons",
                return_value=["cannot verify current boot state"],
            ),
            patch("clusterctl.main.subprocess.run") as run,
        ):
            result = cmd_deploy(args)

        self.assertEqual(result, 0)
        run.assert_not_called()

    def test_boot_manifest_ignores_routine_toplevel_change(self):
        first = """
        {
          "org.nixos.bootspec.v1": {
            "init": "/nix/store/old-system/init",
            "initrd": "/nix/store/initrd/initrd",
            "kernel": "/nix/store/kernel/bzImage",
            "kernelParams": ["root=fstab"],
            "label": "old label",
            "system": "x86_64-linux",
            "toplevel": "/nix/store/old-system"
          },
          "org.nixos.systemd-boot": {"sortKey": "nixos"}
        }
        """
        second = first.replace("old-system", "new-system").replace(
            "old label",
            "new label",
        )

        self.assertEqual(
            deploy_mod._normalize_boot_json(first),
            deploy_mod._normalize_boot_json(second),
        )

    def test_boot_risk_detects_fstab_and_kernel_changes(self):
        current = {
            "boot": {"kernel": "old"},
            "fstab": ["/dev/disk/by-label/root / ext4 defaults 0 1"],
        }
        proposed = {
            "boot": {"kernel": "new"},
            "fstab": ["/dev/disk/by-partlabel/root / ext4 defaults 0 1"],
        }
        with (
            patch(
                "clusterctl.deploy.proposed_boot_manifest",
                return_value=proposed,
            ),
            patch(
                "clusterctl.deploy.current_boot_manifest",
                return_value=current,
            ),
        ):
            reasons = deploy_mod.boot_risk_reasons("t320-0", ".")

        self.assertEqual(
            reasons,
            [
                "generated fstab changes",
                "kernel, initrd, kernel parameters, or bootloader metadata changes",
            ],
        )

    def test_deploy_local_root_elevates_only_deploy_subprocess(self):
        args = argparse.Namespace(
            flake=".",
            hosts=["r640-0"],
            out=Path("/run/cluster-identity"),
            dry_run=False,
            local_root=True,
        )
        with (
            patch(
                "clusterctl.main.transport.inventory",
                return_value={"hosts": {"r640-0": {}}},
            ),
            patch("clusterctl.main.resolve_hosts_arg", return_value=["r640-0"]),
            patch(
                "clusterctl.main.deploy.candidates",
                return_value=[],
            ),
            patch(
                "clusterctl.execution.os.geteuid",
                return_value=1000,
            ),
            patch(
                "clusterctl.execution.sudo_authorization_status",
                return_value=SudoAuthorization.CACHED,
            ),
            patch(
                "clusterctl.main.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0),
            ) as run,
        ):
            self.assertEqual(cmd_deploy(args), 0)

        run.assert_called_once_with(
            [
                "sudo",
                "--",
                "nix",
                "run",
                ".#deploy-rs",
                "--",
                "--skip-checks",
                ".#r640-0",
            ],
            check=False,
        )

    def test_leader_user_is_derived_from_user_inventory(self):
        inventory = {
            "hosts": {
                "desktoptoodle": {
                    "users": ["ash", "madeline"],
                }
            },
            "users": {
                "ash": {
                    "home": {"directory": "/home/example"},
                    "org": {"clusterIdentity": {"role": "leader"}},
                },
                "madeline": {
                    "home": {"directory": "/home/example"},
                },
            },
        }

        self.assertEqual(
            leader_user_for_host(inventory, "desktoptoodle"),
            ("ash", "/home/example/.ssh/cluster-leader-ed25519"),
        )

    def test_status_ipns_generation_uses_local_kubo_for_local_host(self):
        completed = argparse.Namespace(
            stdout="k51-local-status\n",
            stderr="",
        )
        with (
            patch("clusterctl.main.is_local_node", return_value=True),
            patch("clusterctl.main.subprocess.run", return_value=completed) as run,
            patch("clusterctl.main.ssh_completed") as ssh,
        ):
            ipns_name = capture_status_ipns_name("desktoptoodle", ".")

        self.assertEqual(ipns_name, "k51-local-status")
        ssh.assert_not_called()
        run.assert_called_once()

    def test_status_ipns_generation_falls_back_to_sops_key(self):
        inventory = {
            "hosts": {
                "r640-0": {
                    "org": {"clusterIdentity": {"role": "leader"}},
                    "users": ["ash"],
                },
            },
            "users": {
                "ash": {
                    "home": {"directory": "/home/example"},
                    "org": {"clusterIdentity": {"role": "leader"}},
                },
            },
            "identityRequirements": {
                "byHost": {
                    "r640-0": {
                        "status-ipns": {
                            "service": "status-ipns",
                            "generator": "status-ipns",
                            "sourceLedger": "inventory/identity-services/status-ipns.nix",
                            "privateLedger": "inventory/keys/identities/cluster-private-identities.sops.yaml",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "status-ipns": {},
                },
            },
        }
        args = argparse.Namespace(
            flake=".",
            registry=Path("/var/lib/cluster-identity/registry"),
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            node=[],
            service=["status-ipns"],
            dry_run=False,
            sops_age_key_file=Path("/var/lib/cluster-identity/age/host.agekey"),
            publish=False,
            publish_push=False,
            notify=False,
            no_reconcile=False,
            leader=None,
            leader_key=None,
            signing_key=None,
            signature=None,
            no_commit=False,
        )

        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch(
                "clusterctl.main.capture_status_ipns_name",
                side_effect=subprocess.CalledProcessError(255, ["ssh"]),
            ),
            patch(
                "clusterctl.main.generate_ipns_key",
                return_value=("k51-fallback", "PRIVATE"),
            ),
            patch("clusterctl.main.update_sops_string_map") as update_sops,
            patch("clusterctl.main.update_identity_source_file") as update_identity,
            patch("clusterctl.main.stage_flake_paths") as stage,
        ):
            result = cmd_identity_generate_missing(args)

        self.assertEqual(result, 0)
        update_sops.assert_called_once()
        record = update_identity.call_args.args[3]
        self.assertEqual(record["public"]["ipnsName"], "k51-fallback")
        self.assertEqual(record["private"]["sopsKey"], "r640-0-status-ipns")
        stage.assert_called_once()

    def test_status_ipns_generation_reports_unreachable_follower(self):
        inventory = {
            "hosts": {
                "t320-0": {
                    "org": {"clusterIdentity": {"role": "follower"}},
                },
            },
            "identityRequirements": {
                "byHost": {
                    "t320-0": {
                        "status-ipns": {
                            "service": "status-ipns",
                            "generator": "status-ipns",
                            "sourceLedger": "inventory/identity-services/status-ipns.nix",
                            "privateLedger": "inventory/keys/identities/cluster-private-identities.sops.yaml",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "status-ipns": {},
                },
            },
        }
        args = argparse.Namespace(
            flake=".",
            registry=Path("/var/lib/cluster-identity/registry"),
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            node=[],
            service=["status-ipns"],
            dry_run=False,
            sops_age_key_file=Path("/var/lib/cluster-identity/age/host.agekey"),
            publish=False,
            publish_push=False,
            notify=False,
            no_reconcile=False,
            leader=None,
            leader_key=None,
            signing_key=None,
            signature=None,
            no_commit=False,
        )
        printed = []
        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch(
                "clusterctl.main.capture_status_ipns_name",
                side_effect=subprocess.CalledProcessError(255, ["ssh"]),
            ),
            patch(
                "builtins.print",
                side_effect=lambda *parts, **_kw: printed.append(parts),
            ),
        ):
            result = cmd_identity_generate_missing(args)

        self.assertEqual(result, 1)
        printed_text = "\n".join(
            " ".join(str(part) for part in parts) for parts in printed
        )
        self.assertIn("Still manual", printed_text)
        self.assertIn("t320-0/status-ipns", printed_text)

    def test_status_ipns_generation_handles_mixed_cluster_reachability(self):
        cases = [
            {
                "name": "all reachable",
                "roles": {
                    "leader-a": "leader",
                    "follower-a": "follower",
                },
                "unreachable": set(),
                "result": 0,
                "generated": {"leader-a", "follower-a"},
                "manual": set(),
                "sops_fallbacks": 0,
            },
            {
                "name": "unreachable leader falls back",
                "roles": {
                    "leader-a": "leader",
                    "follower-a": "follower",
                },
                "unreachable": {"leader-a"},
                "result": 0,
                "generated": {"leader-a", "follower-a"},
                "manual": set(),
                "sops_fallbacks": 1,
            },
            {
                "name": "unreachable follower stays manual",
                "roles": {
                    "leader-a": "leader",
                    "follower-a": "follower",
                },
                "unreachable": {"follower-a"},
                "result": 1,
                "generated": {"leader-a"},
                "manual": {"follower-a"},
                "sops_fallbacks": 0,
            },
            {
                "name": "mixed leaders and followers",
                "roles": {
                    "leader-a": "leader",
                    "leader-b": "leader",
                    "follower-a": "follower",
                    "follower-b": "follower",
                },
                "unreachable": {"leader-a", "follower-a"},
                "result": 1,
                "generated": {"leader-a", "leader-b", "follower-b"},
                "manual": {"follower-a"},
                "sops_fallbacks": 1,
            },
            {
                "name": "all unreachable leader and follower",
                "roles": {
                    "leader-a": "leader",
                    "follower-a": "follower",
                },
                "unreachable": {"leader-a", "follower-a"},
                "result": 1,
                "generated": {"leader-a"},
                "manual": {"follower-a"},
                "sops_fallbacks": 1,
            },
        ]

        for case in cases:
            with self.subTest(case["name"]):
                inventory = {
                    "hosts": {
                        node: {"org": {"clusterIdentity": {"role": role}}}
                        for node, role in case["roles"].items()
                    },
                    "identityRequirements": {
                        "byHost": {
                            node: {
                                "status-ipns": {
                                    "service": "status-ipns",
                                    "generator": "status-ipns",
                                    "sourceLedger": "inventory/identity-services/status-ipns.nix",
                                    "privateLedger": (
                                        "inventory/keys/identities/"
                                        "cluster-private-identities.sops.yaml"
                                    ),
                                },
                            }
                            for node in case["roles"]
                        },
                    },
                    "identities": {
                        "services": {
                            "status-ipns": {},
                        },
                    },
                }
                args = argparse.Namespace(
                    flake=".",
                    registry=Path("/var/lib/cluster-identity/registry"),
                    out=Path("/run/cluster-identity"),
                    policy=Path("/etc/cluster-identity/policy.json"),
                    node=[],
                    service=["status-ipns"],
                    dry_run=False,
                    sops_age_key_file=Path("/var/lib/cluster-identity/age/host.agekey"),
                    publish=False,
                    publish_push=False,
                    notify=False,
                    no_reconcile=False,
                    leader=None,
                    leader_key=None,
                    signing_key=None,
                    signature=None,
                    no_commit=False,
                )

                def capture(node, _flake):
                    if node in case["unreachable"]:
                        raise subprocess.CalledProcessError(255, ["ssh", node])
                    return f"k51-{node}"

                printed = []
                with (
                    patch(
                        "clusterctl.main.transport.inventory", return_value=inventory
                    ),
                    patch(
                        "clusterctl.main.capture_status_ipns_name", side_effect=capture
                    ),
                    patch(
                        "clusterctl.main.generate_ipns_key",
                        return_value=("k51-fallback", "PRIVATE"),
                    ),
                    patch("clusterctl.main.update_sops_string_map") as update_sops,
                    patch(
                        "clusterctl.main.update_identity_source_file"
                    ) as update_identity,
                    patch("clusterctl.main.stage_flake_paths"),
                    patch(
                        "builtins.print",
                        side_effect=lambda *parts, **_kw: printed.append(parts),
                    ),
                ):
                    result = cmd_identity_generate_missing(args)

                self.assertEqual(result, case["result"])
                generated = {call.args[2] for call in update_identity.call_args_list}
                self.assertEqual(generated, case["generated"])
                self.assertEqual(update_sops.call_count, case["sops_fallbacks"])
                printed_text = "\n".join(
                    " ".join(str(part) for part in parts) for parts in printed
                )
                for node in case["manual"]:
                    self.assertIn(f"{node}/status-ipns", printed_text)
                if not case["manual"]:
                    self.assertNotIn("Still manual", printed_text)

    def test_generate_missing_supports_every_declared_generator(self):
        services = {
            "host-age": {
                "generator": "host-age",
                "sourceLedger": "inventory/keys/host-age-recipients.nix",
            },
            "ipns-publisher": {
                "generator": "ipns-publisher",
                "sourceLedger": "inventory/identity-services/ipns-publisher.nix",
                "privateLedger": "inventory/keys/leaders/leader-ipns-keys.sops.yaml",
                "registryPublish": False,
            },
            "onion-mirror": {
                "generator": "onion-mirror",
                "sourceLedger": "inventory/identity-services/onion-mirror.nix",
                "registryPublish": False,
            },
            "status-ipns": {
                "generator": "status-ipns",
                "sourceLedger": "inventory/identity-services/status-ipns.nix",
                "privateLedger": "inventory/keys/identities/cluster-private-identities.sops.yaml",
            },
            "leader-user-ssh": {
                "generator": "leader-user-ssh",
                "sourceLedger": "inventory/identity-services/leader-user-ssh.nix",
                "privateLedger": "inventory/keys/identities/cluster-private-identities.sops.yaml",
                "registryPublish": False,
            },
            "yggdrasil": {
                "generator": "yggdrasil",
                "sourceLedger": "inventory/identity-services/yggdrasil.nix",
            },
            "ssh-host": {
                "generator": "ssh-host",
                "sourceLedger": "inventory/identity-services/ssh-host.nix",
            },
            "radicle": {
                "generator": "radicle",
                "sourceLedger": "inventory/identity-services/radicle.nix",
            },
            "git-annex": {
                "generator": "git-annex",
                "sourceLedger": "inventory/identity-services/git-annex.nix",
            },
        }
        inventory = {
            "hosts": {
                "node-a": {
                    "users": ["ash"],
                },
            },
            "users": {
                "ash": {
                    "home": {"directory": "/home/example"},
                    "org": {"clusterIdentity": {"role": "leader"}},
                },
            },
            "identityRequirements": {
                "byHost": {
                    "node-a": {
                        service: {"service": service, **requirement}
                        for service, requirement in services.items()
                    },
                },
            },
            "identities": {
                "services": {service: {} for service in services},
            },
        }
        args = argparse.Namespace(
            flake=".",
            registry=Path("/var/lib/cluster-identity/registry"),
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            node=[],
            service=[],
            dry_run=False,
            sops_age_key_file=Path("/var/lib/cluster-identity/age/host.agekey"),
            publish=False,
            publish_push=False,
            notify=False,
            no_reconcile=False,
            leader=None,
            leader_key=None,
            signing_key=None,
            signature=None,
            no_commit=False,
        )

        printed = []
        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch("clusterctl.main.ensure_host_age_key", return_value="age1node"),
            patch(
                "clusterctl.main.generate_ipns_key",
                return_value=("k51-leader", "PRIVATE"),
            ),
            patch(
                "clusterctl.main.capture_onion_mirror_identity",
                return_value={
                    "publicKeyFileBase64": (
                        "PT0gZWQyNTUxOXYxLXB1YmxpYzogdHlwZTAgPT0AAABr+"
                        "MOEhhlRzqfbKD/WXRAE0neGJHsKil3fqziktz4xhw=="
                    ),
                    "onionAddress": (
                        "np4mhbegdfi45j63fa75mxiqatjhpbrepmfiuxo7vm4kjnz6ggdvofad.onion"
                    ),
                },
            ),
            patch(
                "clusterctl.main.capture_status_ipns_name", return_value="k51-status"
            ),
            patch(
                "clusterctl.main.generate_ssh_key",
                return_value=("ssh-ed25519 PUBLIC", "PRIVATE"),
            ),
            patch(
                "clusterctl.main.capture_yggdrasil_public",
                return_value={"publicKey": "yggpub", "address": "200::1"},
            ),
            patch(
                "clusterctl.main.capture_ssh_host_key", return_value="ssh-ed25519 HOST"
            ),
            patch("clusterctl.main.capture_radicle_node_id", return_value="zRadicle"),
            patch(
                "clusterctl.main.derive_git_annex_payload",
                return_value={
                    "gitAnnexEndpoint": "annex+ssh://node-a-ygg/srv/annex",
                    "repoRoot": "/srv/annex",
                    "hostAlias": "node-a-ygg",
                },
            ),
            patch("clusterctl.main.update_host_age_recipient_file"),
            patch("clusterctl.main.update_identity_source_file") as update_identity,
            patch("clusterctl.main.update_sops_string_map"),
            patch("clusterctl.main.stage_flake_paths"),
            patch(
                "builtins.print",
                side_effect=lambda *parts, **_kw: printed.append(parts),
            ),
        ):
            result = cmd_identity_generate_missing(args)

        self.assertEqual(result, 0)
        printed_text = "\n".join(
            " ".join(str(part) for part in parts) for parts in printed
        )
        self.assertNotIn("Still manual", printed_text)
        generated_services = {call.args[1] for call in update_identity.call_args_list}
        self.assertEqual(
            generated_services,
            set(services) - {"host-age"},
        )

    def test_generate_missing_reports_remote_capture_failures_without_traceback(self):
        inventory = {
            "hosts": {
                "node-a": {},
            },
            "identityRequirements": {
                "byHost": {
                    "node-a": {
                        "onion-mirror": {
                            "service": "onion-mirror",
                            "generator": "onion-mirror",
                            "sourceLedger": "inventory/identity-services/onion-mirror.nix",
                            "registryPublish": False,
                        },
                        "git-annex": {
                            "service": "git-annex",
                            "generator": "git-annex",
                            "sourceLedger": "inventory/identity-services/git-annex.nix",
                        },
                    },
                },
            },
            "identities": {
                "services": {
                    "onion-mirror": {},
                    "git-annex": {},
                },
            },
        }
        args = argparse.Namespace(
            flake=".",
            registry=Path("/var/lib/cluster-identity/registry"),
            out=Path("/run/cluster-identity"),
            policy=Path("/etc/cluster-identity/policy.json"),
            node=[],
            service=[],
            all=True,
            dry_run=False,
            sops_age_key_file=Path("/var/lib/cluster-identity/age/host.agekey"),
            publish=False,
            publish_push=False,
            notify=False,
            no_reconcile=False,
            leader=None,
            leader_key=None,
            signing_key=None,
            signature=None,
            no_commit=False,
        )

        printed = []
        with (
            patch("clusterctl.main.transport.inventory", return_value=inventory),
            patch(
                "clusterctl.main.capture_onion_mirror_identity",
                side_effect=subprocess.CalledProcessError(
                    255,
                    ["ssh", "root@node-a"],
                    stderr="host unreachable",
                ),
            ),
            patch(
                "clusterctl.main.derive_git_annex_payload",
                return_value={
                    "gitAnnexEndpoint": "annex+ssh://node-a/srv/annex",
                    "repoRoot": "/srv/annex",
                    "hostAlias": "node-a",
                },
            ),
            patch("clusterctl.main.update_identity_source_file") as update_identity,
            patch(
                "builtins.print",
                side_effect=lambda *parts, **_kw: printed.append(parts),
            ),
        ):
            result = cmd_identity_generate_missing(args)

        self.assertEqual(result, 1)
        update_identity.assert_called_once()
        self.assertEqual(update_identity.call_args.args[1], "git-annex")
        printed_text = "\n".join(
            " ".join(str(part) for part in parts) for parts in printed
        )
        self.assertIn("Failed automatic generation", printed_text)
        self.assertIn("node-a/onion-mirror", printed_text)
        self.assertIn("host unreachable", printed_text)

    def test_onion_mirror_capture_derives_hostname_from_public_key(self):
        public_key = (
            "PT0gZWQyNTUxOXYxLXB1YmxpYzogdHlwZTAgPT0AAABr+"
            "MOEhhlRzqfbKD/WXRAE0neGJHsKil3fqziktz4xhw=="
        )
        hostname = "np4mhbegdfi45j63fa75mxiqatjhpbrepmfiuxo7vm4kjnz6ggdvofad.onion"
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                '{"publicKeyFileBase64":"'
                + public_key
                + '","hostname":"'
                + hostname
                + '"}'
            ),
        )

        with patch("clusterctl.main.ssh_completed", return_value=completed):
            payload = capture_onion_mirror_identity("desktoptoodle", ".")

        self.assertEqual(payload["publicKeyFileBase64"], public_key)
        self.assertEqual(payload["onionAddress"], hostname)

    def test_generated_identity_publication_stays_in_process_when_writable(self):
        with (
            patch("clusterctl.main.identity_publish_requires_sudo", return_value=False),
            patch("clusterctl.main.cmd_identity_publish", return_value=7) as publish,
        ):
            result = publish_generated_identities(self.publish_args())

        self.assertEqual(result, 7)
        publish.assert_called_once()

    def test_identity_publish_refuses_cross_leader_local_inventory_write(self):
        args = self.publish_args()
        args.leader = "leader-b"
        policy = {"hostName": "leader-a", "registry": {}}
        with (
            patch("clusterctl.main.load_policy", return_value=policy),
            patch("clusterctl.main.ensure_registry_git_repo") as ensure,
            patch("clusterctl.main.transport.inventory") as inventory,
        ):
            result = cmd_identity_publish(args)

        self.assertEqual(result, 1)
        ensure.assert_not_called()
        inventory.assert_not_called()

    def test_identity_publish_allows_explicit_cross_leader_deploy_publication(self):
        args = self.publish_args()
        args.leader = "leader-b"
        args.allow_cross_leader_publish = True
        policy = {"hostName": "leader-a", "registry": {}}
        with (
            patch("clusterctl.main.load_policy", return_value=policy),
            patch("clusterctl.main.ensure_registry_git_repo"),
            patch(
                "clusterctl.main.transport.inventory", return_value={"identities": {}}
            ),
            patch("clusterctl.main.registry.reconcile"),
        ):
            result = cmd_identity_publish(args)

        self.assertEqual(result, 0)

    def test_generated_identity_publication_detects_root_owned_registry(self):
        with (
            patch("clusterctl.main.os.geteuid", return_value=1000),
            patch(
                "clusterctl.main.path_is_accessible", return_value=False
            ) as accessible,
            patch.dict("clusterctl.main.os.environ", {}, clear=True),
        ):
            requires_sudo = identity_publish_requires_sudo(self.publish_args())

        self.assertTrue(requires_sudo)
        accessible.assert_called_once_with(
            Path("/var/lib/cluster-identity/registry"),
            os.R_OK | os.W_OK | os.X_OK,
        )

    def test_ensure_v1_archives_legacy_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = root / "registry"
            events = registry / "events"
            events.mkdir(parents=True)
            (events / "identity-legacy.json").write_text(
                '{"schema":"legacy"}\n', encoding="utf-8"
            )

            result = cmd_registry_ensure_v1(
                argparse.Namespace(registry=registry, no_commit=False)
            )

            self.assertEqual(result, 0)
            self.assertTrue((registry / ".git").is_dir())
            self.assertEqual(list((registry / "events").glob("*.json")), [])
            archives = list(root.glob("registry-pre-v1-*"))
            self.assertEqual(len(archives), 1)
            self.assertTrue((archives[0] / "events" / "identity-legacy.json").is_file())

    def test_supersedence_record_is_compatible_with_v1_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            registry = Path(temporary) / "registry"
            write_json(
                registry / "events" / "leader-a" / "000000000001.json",
                {"schema": "cluster.identity.supersedence.v1"},
            )

            self.assertFalse(registry_needs_v1_reseed(registry))

    def test_host_signing_key_overrides_legacy_global_policy_key(self):
        policy = {
            "signingKeyPath": "/root/.ssh/id_ed25519",
            "policy": {
                "signingKeyPath": "/home/example/.ssh/deploy_rsa",
            },
        }

        self.assertEqual(
            signing_key_path(policy),
            Path("/root/.ssh/id_ed25519"),
        )

    def test_existing_identity_comparison_accounts_for_derived_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            registry = Path(temporary)
            event_path = registry / "events" / "leader-a" / "000000000001.json"
            write_json(
                event_path,
                {
                    "subject": {"node": "node-a", "service": "ssh-host"},
                    "generation": 1,
                    "state": "active",
                    "public": {
                        "sshHostKey": "ssh-ed25519 test",
                        "fingerprint": "sha256:1351cac34a8533ede5c36b21e452ca0bb2498bf1ac5b2830cb8c29a513f1af20",
                    },
                    "privateDelivery": None,
                },
            )

            self.assertTrue(
                registry_already_has_identity(
                    registry,
                    "node-a",
                    "ssh-host",
                    1,
                    "active",
                    {"sshHostKey": "ssh-ed25519 test"},
                    None,
                )
            )


if __name__ == "__main__":
    unittest.main()
