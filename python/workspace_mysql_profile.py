"""Small, durable MySQL profile for private local recording workspaces.

Waveforms live in H5; SQL stores metadata and user-authored state. Keep crash
recovery and durable commits. Replication/PITR is not an app-managed workflow;
backups must be explicit snapshots, not an accumulating binary log.
"""


def local_mysql_options(*, legacy_redo=False):
    # datajoint/mysql:8.0 includes pre-8.0.30 servers. The bundled native
    # MySQL 8.4 uses redo capacity; the legacy two-file settings were removed.
    redo = ('--innodb-log-file-size=32M', '--innodb-log-files-in-group=2') if legacy_redo else (
        '--innodb-redo-log-capacity=64M',)
    return (*redo, '--skip-log-bin', '--innodb-buffer-pool-size=128M',
            '--innodb-flush-log-at-trx-commit=1', '--innodb-doublewrite=ON')
