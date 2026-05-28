import os
import subprocess
import logging
from typing import List

class GitController:
    def __init__(self):
        self.logger = logging.getLogger("Jarvis.GitControl")

    def _run_git(self, repo_path: str, args: List[str]) -> str:
        """Runs a git command inside the specified repo path."""
        cmd = ["git"] + args
        self.logger.info(f"Running git command: {' '.join(cmd)} in {repo_path}")
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git command failed: {e.stderr}")
            raise RuntimeError(f"Git execution error: {e.stderr.strip()}")

    def git_init(self, repo_path: str) -> str:
        return self._run_git(repo_path, ["init"])

    def git_add_all(self, repo_path: str) -> str:
        return self._run_git(repo_path, ["add", "."])

    def git_commit(self, repo_path: str, message: str) -> str:
        return self._run_git(repo_path, ["commit", "-m", message])

    def git_clone(self, repo_url: str, dest_path: str) -> str:
        """Clones a remote repository to dest_path."""
        self.logger.info(f"Cloning {repo_url} to {dest_path}...")
        try:
            # Clone doesn't need to be run in cwd because it creates the dir
            result = subprocess.run(
                ["git", "clone", repo_url, dest_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git clone failed: {e.stderr}")
            raise RuntimeError(f"Git clone execution error: {e.stderr.strip()}")

    def git_push(self, repo_path: str, remote: str = "origin", branch: str = "main") -> str:
        return self._run_git(repo_path, ["push", remote, branch])

    def git_status(self, repo_path: str) -> str:
        return self._run_git(repo_path, ["status"])

    def git_checkout(self, repo_path: str, branch: str, create: bool = False) -> str:
        """Checks out a branch, optionally creating it first."""
        args = ["checkout", "-b", branch] if create else ["checkout", branch]
        return self._run_git(repo_path, args)

    def git_merge(self, repo_path: str, branch: str) -> str:
        """Merges another branch into the active branch."""
        return self._run_git(repo_path, ["merge", branch])

    def git_delete_branch(self, repo_path: str, branch: str, delete_remote: bool = False) -> str:
        """Deletes a local branch, and optionally a remote branch on origin."""
        res = self._run_git(repo_path, ["branch", "-d", branch])
        if delete_remote:
            try:
                res += "\n" + self._run_git(repo_path, ["push", "origin", "--delete", branch])
            except Exception as e:
                res += f"\nFailed to delete remote branch: {e}"
        return res

    def git_pull(self, repo_path: str, remote: str = "origin", branch: str = "main") -> str:
        """Pulls changes from a remote branch."""
        return self._run_git(repo_path, ["pull", remote, branch])

    def git_branch_list(self, repo_path: str) -> str:
        """Lists local and remote branches."""
        return self._run_git(repo_path, ["branch", "-a"])

    def git_log(self, repo_path: str, limit: int = 5) -> str:
        """Displays commit log."""
        return self._run_git(repo_path, ["log", f"-n", str(limit), "--oneline"])

    def git_remote_list(self, repo_path: str) -> str:
        """Lists configured remotes."""
        return self._run_git(repo_path, ["remote", "-v"])

    def git_fetch(self, repo_path: str) -> str:
        """Fetches remote updates."""
        return self._run_git(repo_path, ["fetch"])

