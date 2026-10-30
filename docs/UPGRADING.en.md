# Upgrade in place

The update baseline is the pushed v0.6 commit `9e02c9fdaaf6a106e05ed37acfa5928b8640f4d8`. Application releases and named catalogue workspaces are separate. Updating the application must preserve your existing folder, environment and workspace data.

1. Choose **Stop service & exit** in the old tray menu. Hiding the launcher is insufficient.
2. Extract the small update bundle, or the new complete release, into a temporary location.
3. Run **the new package's `Update_Atlas.cmd`** and select your existing application folder. You can also drag that folder onto the CMD file.
4. The updater validates checksums and local changes, backs up managed application files and applies the included migration chain. It restarts the application from its original path after success.

Do not replace the entire old folder or overwrite its `data` directory. The existing folder name can remain unchanged even when it contains an older version number. `.venv`, named workspaces, favourites, history, settings, secrets, operation counts, media and retained caches remain in place. The v0.6→v0.7 third-party requirements are unchanged, so the updater does not reinstall them. Startup uses uv's inexact synchronization to retain extra packages.

Backups and step events are in `data/updates/<transaction>/`. `data/install_state.json` and `data/update_history.jsonl` record application upgrades outside catalogue workspace management. Changed local code, unapproved paths, symlinks, junctions and payload checksum failures stop the update. Ordinary failures roll back the entire chain; a failed restoration names the remaining paths. Power loss or forced termination cannot guarantee automatic rollback, so keep the backup.

Future bundles can include consecutive 0.6→0.7→0.8→0.9 steps and restart once after the final commit. This bundle includes only the real v0.7 step; future releases and migrations do not exist yet. If a future step changes dependencies, the existing environment is backed up before reconciliation and restored on failure.

```bash
python update.py --target /path/to/existing-atlas --dry-run
python update.py --target /path/to/existing-atlas --restart
```

On macOS/Linux, run `bash Update_Atlas.sh /path/to/existing-atlas`. The updater does not automatically fetch GitHub or install the optional browser helper. See the [Chinese guide](UPGRADING.zh-CN.md) for details.
