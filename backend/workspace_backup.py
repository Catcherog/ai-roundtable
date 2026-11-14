"""Git worktree and index snapshots for one roundtable execution."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


def _git(cwd, *args, env=None, data=None):
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(cwd), *args],
        input=data if data is not None else b"",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=90,
    )
    if result.returncode:
        raise ValueError(os.fsdecode(result.stderr).strip() or "Git 快照操作失败")
    return result.stdout


class WorkspaceBackup:
    def __init__(self, cwd, root):
        self.cwd = cwd
        self.root = root
        self.storage = tempfile.TemporaryDirectory(prefix="ai-roundtable-snapshot-")
        directory = Path(self.storage.name)
        objects = directory / "objects"
        objects.mkdir()
        repo_objects = _git(root, "rev-parse", "--git-path", "objects").rstrip(b"\n")
        repo_objects = os.path.abspath(os.path.join(root, os.fsdecode(repo_objects)))
        # The private object store keeps untracked files out of the repository after this session.
        alternates = json.dumps(repo_objects, ensure_ascii=False)
        if os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            alternates += os.pathsep + os.environ["GIT_ALTERNATE_OBJECT_DIRECTORIES"]
        self.env = dict(os.environ, GIT_INDEX_FILE=str(directory / "index"),
                        GIT_OBJECT_DIRECTORY=str(objects), GIT_ALTERNATE_OBJECT_DIRECTORIES=alternates)
        self.before = self._trees()
        self.after = None
        self.patches = ()

    @classmethod
    def capture(cls, cwd):
        try:
            root = os.fsdecode(_git(cwd, "rev-parse", "--show-toplevel").rstrip(b"\n"))
        except (ValueError, FileNotFoundError):
            return None
        return cls(cwd, root)

    def _trees(self):
        # Use only this workspace's entries, even when it is a subdirectory of a repository.
        entries = _git(self.cwd, "ls-files", "--full-name", "--stage", "-z", "--", ".")
        _git(self.root, "read-tree", "--empty", env=self.env)
        _git(self.root, "update-index", "-z", "--index-info", data=entries, env=self.env)
        index = _git(self.root, "write-tree", env=self.env).strip()
        _git(self.cwd, "add", "-A", "--", ".", env=self.env)
        worktree = _git(self.root, "write-tree", env=self.env).strip()
        return index, worktree

    def _diff(self, before, after, *options):
        return _git(self.root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                    *options, before, after, "--", env=self.env)

    def finish(self):
        self.after = self._trees()
        self.patches = tuple(
            self._diff(before, after, "--binary", "--src-prefix=a/", "--dst-prefix=b/")
            if before != after else b""
            for before, after in zip(self.before, self.after)
        )
        return any(self.patches)

    @property
    def worktree_diff(self):
        return self.patches[1].decode("utf-8", errors="replace")

    def restore(self):
        if self.after is None:
            return False, "本次执行尚未完成，暂无可回滚的快照"
        current = self._trees()
        # A file can change in either the worktree or the index after execution, e.g. git add.
        affected = set()
        later = set()
        for before, after, now in zip(self.before, self.after, current):
            if before != after:
                affected.update(self._diff(before, after, "--name-only", "-z").split(b"\0")[:-1])
            if now != after:
                later.update(self._diff(after, now, "--name-only", "-z").split(b"\0")[:-1])
        conflicts = affected & later
        if conflicts:
            paths = "、".join(os.fsdecode(p) for p in sorted(conflicts)[:3])
            return False, f"以下文件在执行结束后又有改动，已保留当前内容：{paths}"

        commands = [(("--cached",), self.patches[0]), ((), self.patches[1])]
        commands = [(flags, patch) for flags, patch in commands if patch]
        for flags, patch in commands:
            _git(self.root, "apply", "--check", "--reverse", "--whitespace=nowarn", *flags, "-", data=patch)
        applied = []
        try:
            for flags, patch in commands:
                _git(self.root, "apply", "--reverse", "--whitespace=nowarn", *flags, "-", data=patch)
                applied.append((flags, patch))
        except (ValueError, OSError, subprocess.SubprocessError):
            for flags, patch in reversed(applied):
                _git(self.root, "apply", "--whitespace=nowarn", *flags, "-", data=patch)
            raise
        return True, f"已回滚本次执行的 {len(affected)} 个文件，恢复了原有工作区和暂存内容"
