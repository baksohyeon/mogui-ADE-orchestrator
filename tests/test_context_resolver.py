from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from master_runtime.core.context.descriptor import ContextKind, RepoStatus
from master_runtime.core.context.manifest import (
    ManifestError,
    RepositoryDeclaration,
    WorkspaceManifest,
)
from master_runtime.core.context.resolver import resolve


class ContextFixture:
    def __init__(self, test_case: unittest.TestCase) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        test_case.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name)

    def mkdir(self, relative_path: str) -> Path:
        path = self.root / relative_path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def touch(self, relative_path: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def git_repo(self, relative_path: str) -> Path:
        path = self.mkdir(relative_path)
        (path / ".git").mkdir()
        return path

    def git_worktree(self, relative_path: str) -> Path:
        path = self.mkdir(relative_path)
        (path / ".git").write_text("gitdir: /opaque/git/dir\n", encoding="utf-8")
        return path

    def manifest(
        self,
        repositories: list[tuple[str, str]],
        workspace_identity: str = "workspace:test",
    ) -> WorkspaceManifest:
        declarations = [
            RepositoryDeclaration(path=path, identity=identity, metadata={})
            for path, identity in repositories
        ]
        return WorkspaceManifest(
            workspace_root=self.root,
            workspace_identity=workspace_identity,
            repositories=declarations,
        )

    def manifest_file(self, payload: dict[str, Any]) -> Path:
        path = self.root / "workspace.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


class ContextResolverTests(unittest.TestCase):
    def test_case_a_declared_multi_repo_workspace(self) -> None:
        fixture = ContextFixture(self)
        fixture.git_repo("backend")
        fixture.git_repo("frontend")
        fixture.git_repo("planning")
        manifest = fixture.manifest(
            [
                ("backend", "repo:backend"),
                ("frontend", "repo:frontend"),
                ("planning", "repo:planning"),
            ]
        )

        descriptor = resolve(fixture.root, manifest)

        self.assertEqual(descriptor.kind, ContextKind.MULTI_REPO_WORKSPACE)
        self.assertFalse(descriptor.capabilities.git_repo)
        self.assertEqual(descriptor.repository_identity, None)
        self.assertEqual(descriptor.warnings, ())
        self.assertEqual(len(descriptor.repo_set), 3)
        self.assertEqual(
            {entry.status for entry in descriptor.repo_set},
            {RepoStatus.DECLARED_OBSERVED},
        )

    def test_case_b_folder_descriptor_has_no_git_capability(self) -> None:
        fixture = ContextFixture(self)
        folder = fixture.mkdir("notes")
        manifest = fixture.manifest([])

        descriptor = resolve(folder, manifest)

        self.assertEqual(descriptor.kind, ContextKind.FOLDER)
        self.assertFalse(descriptor.capabilities.git_repo)

    def test_case_c_plain_folder_descriptor_is_stable(self) -> None:
        fixture = ContextFixture(self)
        folder = fixture.mkdir("plain")
        manifest = fixture.manifest([])

        first = resolve(folder, manifest)
        second = resolve(folder, manifest)

        self.assertEqual(first, second)
        self.assertEqual(first.kind, ContextKind.FOLDER)
        self.assertEqual(first.warnings, ())

    def test_workspace_root_git_marker_takes_precedence_over_workspace_kind(self) -> None:
        fixture = ContextFixture(self)
        fixture.git_repo(".")
        manifest = fixture.manifest([])

        descriptor = resolve(fixture.root, manifest)

        self.assertEqual(descriptor.kind, ContextKind.GIT_REPO)
        self.assertTrue(descriptor.capabilities.git_repo)
        self.assertEqual(descriptor.repository_identity, "observed:.")
        self.assertIn("Observed undeclared repository: .", descriptor.warnings)

    def test_declared_missing_is_data_not_exception(self) -> None:
        fixture = ContextFixture(self)
        manifest = fixture.manifest([("backend", "repo:backend")])

        descriptor = resolve(fixture.root, manifest)

        self.assertEqual(descriptor.kind, ContextKind.MULTI_REPO_WORKSPACE)
        self.assertEqual(len(descriptor.repo_set), 1)
        self.assertEqual(descriptor.repo_set[0].status, RepoStatus.DECLARED_MISSING)
        self.assertIn("Declared repository missing on disk", descriptor.warnings[0])

    def test_observed_undeclared_immediate_child_is_reported(self) -> None:
        fixture = ContextFixture(self)
        fixture.git_repo("scratch")
        manifest = fixture.manifest([])

        descriptor = resolve(fixture.root, manifest)

        self.assertEqual(len(descriptor.repo_set), 1)
        self.assertEqual(descriptor.repo_set[0].status, RepoStatus.OBSERVED_UNDECLARED)
        self.assertEqual(descriptor.repo_set[0].identity, "observed:scratch")
        self.assertIn("Observed undeclared repository: scratch", descriptor.warnings)

    def test_nested_repo_resolves_as_nested_repo(self) -> None:
        fixture = ContextFixture(self)
        fixture.git_repo("backend")
        nested = fixture.git_repo("backend/vendor/inner")
        manifest = fixture.manifest([("backend", "repo:backend")])

        descriptor = resolve(nested, manifest)

        self.assertEqual(descriptor.kind, ContextKind.NESTED_REPO)
        self.assertTrue(descriptor.capabilities.git_repo)
        self.assertEqual(descriptor.repository_identity, "observed:backend/vendor/inner")
        self.assertIn(RepoStatus.OBSERVED_UNDECLARED, {entry.status for entry in descriptor.repo_set})
        self.assertTrue(any("Nested repository" in warning for warning in descriptor.warnings))

    def test_gitdir_file_resolves_as_worktree(self) -> None:
        fixture = ContextFixture(self)
        worktree = fixture.git_worktree("frontend")
        manifest = fixture.manifest([("frontend", "repo:frontend")])

        descriptor = resolve(worktree, manifest)

        self.assertEqual(descriptor.kind, ContextKind.GIT_WORKTREE)
        self.assertTrue(descriptor.capabilities.git_repo)
        self.assertEqual(descriptor.repository_identity, "repo:frontend")

    def test_deep_file_uses_longest_path_membership(self) -> None:
        fixture = ContextFixture(self)
        fixture.git_repo("backend")
        fixture.git_repo("backend/packages/service")
        file_path = fixture.touch("backend/packages/service/src/module.py")
        manifest = fixture.manifest(
            [
                ("backend", "repo:backend"),
                ("backend/packages/service", "repo:service"),
            ]
        )

        descriptor = resolve(file_path, manifest)

        self.assertEqual(descriptor.kind, ContextKind.NESTED_REPO)
        self.assertEqual(descriptor.repository_identity, "repo:service")
        self.assertEqual(
            {entry.status for entry in descriptor.repo_set},
            {RepoStatus.DECLARED_OBSERVED},
        )

    def test_malformed_manifest_raises_manifest_error(self) -> None:
        fixture = ContextFixture(self)
        missing = fixture.root / "missing.json"
        invalid_json = fixture.root / "invalid.json"
        invalid_json.write_text("{", encoding="utf-8")
        missing_keys = fixture.manifest_file({"workspace_root": str(fixture.root)})

        for manifest_path in (missing, invalid_json, missing_keys):
            with self.subTest(manifest_path=manifest_path):
                with self.assertRaises(ManifestError):
                    resolve(fixture.root, manifest_path)

    def test_non_object_repository_entries_raise_manifest_error(self) -> None:
        fixture = ContextFixture(self)
        manifest_path = fixture.manifest_file(
            {
                "workspace_root": str(fixture.root),
                "workspace_identity": "workspace:test",
                "repositories": ["backend"],
            }
        )

        with self.assertRaises(ManifestError):
            resolve(fixture.root, manifest_path)

    def test_manifest_constructor_wraps_malformed_collections(self) -> None:
        fixture = ContextFixture(self)

        with self.assertRaises(ManifestError):
            WorkspaceManifest(
                workspace_root=fixture.root,
                workspace_identity="workspace:test",
                repositories=object(),  # type: ignore[arg-type]
            )

        with self.assertRaises(ManifestError):
            WorkspaceManifest(
                workspace_root=fixture.root,
                workspace_identity="workspace:test",
                repositories=[object()],  # type: ignore[list-item]
            )

        with self.assertRaises(ManifestError):
            WorkspaceManifest(
                workspace_root=fixture.root,
                workspace_identity="workspace:test",
                repositories=[],
                metadata=object(),  # type: ignore[arg-type]
            )

    def test_normalized_declared_path_identity_collision_raises_manifest_error(self) -> None:
        fixture = ContextFixture(self)
        fixture.git_repo("backend")
        manifest = WorkspaceManifest(
            workspace_root=fixture.root,
            workspace_identity="workspace:test",
            repositories=[
                {"path": "backend", "identity": "repo:backend"},
                {"path": "./backend", "identity": "repo:other-backend"},
            ],
        )

        with self.assertRaises(ManifestError):
            resolve(fixture.root, manifest)

    def test_workspace_child_listing_failure_is_reported_as_warning(self) -> None:
        fixture = ContextFixture(self)
        manifest = fixture.manifest([])
        original_iterdir = Path.iterdir
        expected_root = fixture.root.resolve(strict=False)

        def failing_iterdir(path: Path) -> Any:
            if path.resolve(strict=False) == expected_root:
                raise OSError("permission denied")
            return original_iterdir(path)

        with patch.object(Path, "iterdir", failing_iterdir):
            descriptor = resolve(fixture.root, manifest)

        self.assertEqual(descriptor.kind, ContextKind.MULTI_REPO_WORKSPACE)
        self.assertTrue(
            any("Could not list workspace children" in warning for warning in descriptor.warnings)
        )

    def test_descriptor_warnings_are_immutable_tuple(self) -> None:
        fixture = ContextFixture(self)
        manifest = fixture.manifest([("backend", "repo:backend")])

        descriptor = resolve(fixture.root, manifest)

        self.assertIsInstance(descriptor.warnings, tuple)
        self.assertFalse(hasattr(descriptor.warnings, "append"))

    def test_git_marker_file_is_not_full_read(self) -> None:
        fixture = ContextFixture(self)
        worktree = fixture.git_worktree("frontend")
        manifest = fixture.manifest([("frontend", "repo:frontend")])

        with patch.object(Path, "read_text", side_effect=AssertionError("full read")):
            descriptor = resolve(worktree, manifest)

        self.assertEqual(descriptor.kind, ContextKind.GIT_WORKTREE)

    def test_path_local_recursive_repo_discovery_is_non_goal(self) -> None:
        fixture = ContextFixture(self)
        hidden_repo = fixture.git_repo("scratch/deep/repo")
        manifest = fixture.manifest([])

        descriptor = resolve(fixture.root, manifest)

        self.assertNotIn(str(hidden_repo), {entry.path for entry in descriptor.repo_set})


if __name__ == "__main__":
    unittest.main()
