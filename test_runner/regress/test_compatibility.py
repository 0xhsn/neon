import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import pytest
import toml  # TODO: replace with tomllib for Python >= 3.11
from fixtures.log_helper import log
from fixtures.neon_fixtures import (
    NeonCli,
    NeonEnvBuilder,
    PageserverHttpClient,
    PgBin,
    PortDistributor,
    wait_for_last_record_lsn,
    wait_for_upload,
)
from fixtures.types import Lsn
from pytest import FixtureRequest

#
# A test suite that help to prevent unintentionally breaking backward or forward compatibility between Neon releases.
# - `test_create_snapshot` a script wrapped in a test that creates a data snapshot.
# - `test_backward_compatibility` checks that the current version of Neon can start/read/interract with a data snapshot created by the previous version.
#   The path to the snapshot is configured by COMPATIBILITY_SNAPSHOT_DIR environment variable.
#   If the breakage is intentional, the test can be xfaild with setting ALLOW_BACKWARD_COMPATIBILITY_BREAKAGE=true.
# - `test_forward_compatibility` checks that a snapshot created by the current version can be started/read/interracted by the previous version of Neon.
#   Paths to Neon and Postgres are configured by COMPATIBILITY_NEON_BIN and COMPATIBILITY_POSTGRES_DISTRIB_DIR environment variables.
#   If the breakage is intentional, the test can be xfaild with setting ALLOW_FORWARD_COMPATIBILITY_BREAKAGE=true.
#
# The file contains a couple of helper functions:
# - prepare_snapshot copies the snapshot, cleans it up and makes it ready for the current version of Neon (replaces paths and ports in config files).
# - check_neon_works performs the test itself, feel free to add more checks there.
#


# Note: if renaming this test, don't forget to update a reference to it in a workflow file:
# "Upload compatibility snapshot" step in .github/actions/run-python-test-set/action.yml
@pytest.mark.xdist_group("compatibility")
@pytest.mark.order(before="test_forward_compatibility")
def test_create_snapshot(neon_env_builder: NeonEnvBuilder, pg_bin: PgBin, test_output_dir: Path):
    # The test doesn't really test anything
    # it creates a new snapshot for releases after we tested the current version against the previous snapshot in `test_backward_compatibility`.
    #
    # There's no cleanup here, it allows to adjust the data in `test_backward_compatibility` itself without re-collecting it.
    neon_env_builder.pg_version = "14"
    neon_env_builder.num_safekeepers = 3
    neon_env_builder.enable_local_fs_remote_storage()
    neon_env_builder.preserve_database_files = True

    env = neon_env_builder.init_start()
    pg = env.postgres.create_start("main")

    # FIXME: Is this expected?
    env.pageserver.allowed_errors.append(
        ".*init_tenant_mgr: marking .* as locally complete, while it doesnt exist in remote index.*"
    )

    pg_bin.run(["pgbench", "--initialize", "--scale=10", pg.connstr()])
    pg_bin.run(["pgbench", "--time=60", "--progress=2", pg.connstr()])
    pg_bin.run(["pg_dumpall", f"--dbname={pg.connstr()}", f"--file={test_output_dir / 'dump.sql'}"])

    snapshot_config = toml.load(test_output_dir / "repo" / "config")
    tenant_id = snapshot_config["default_tenant_id"]
    timeline_id = dict(snapshot_config["branch_name_mappings"]["main"])[tenant_id]

    pageserver_http = env.pageserver.http_client()
    lsn = Lsn(pg.safe_psql("SELECT pg_current_wal_flush_lsn()")[0][0])

    wait_for_last_record_lsn(pageserver_http, tenant_id, timeline_id, lsn)
    pageserver_http.timeline_checkpoint(tenant_id, timeline_id)
    wait_for_upload(pageserver_http, tenant_id, timeline_id, lsn)

    env.postgres.stop_all()
    for sk in env.safekeepers:
        sk.stop()
    env.pageserver.stop()

    shutil.copytree(test_output_dir, test_output_dir / "compatibility_snapshot_pg14")
    # Directory `test_output_dir / "compatibility_snapshot_pg14"` is uploaded to S3 in a workflow, keep the name in sync with it


@pytest.mark.xdist_group("compatibility")
@pytest.mark.order(after="test_create_snapshot")
def test_backward_compatibility(
    pg_bin: PgBin,
    port_distributor: PortDistributor,
    test_output_dir: Path,
    neon_binpath: Path,
    pg_distrib_dir: Path,
    pg_version: str,
    request: FixtureRequest,
):
    compatibility_snapshot_dir_env = os.environ.get("COMPATIBILITY_SNAPSHOT_DIR")
    assert (
        compatibility_snapshot_dir_env is not None
    ), "COMPATIBILITY_SNAPSHOT_DIR is not set. It should be set to `compatibility_snapshot_pg14` path generateted by test_create_snapshot (ideally generated by the previous version of Neon)"
    compatibility_snapshot_dir = Path(compatibility_snapshot_dir_env).resolve()

    breaking_changes_allowed = (
        os.environ.get("ALLOW_BACKWARD_COMPATIBILITY_BREAKAGE", "false").lower() == "true"
    )

    try:
        # Copy the snapshot to current directory, and prepare for the test
        prepare_snapshot(
            from_dir=compatibility_snapshot_dir,
            to_dir=test_output_dir / "compatibility_snapshot",
            neon_binpath=neon_binpath,
            port_distributor=port_distributor,
        )

        check_neon_works(
            test_output_dir / "compatibility_snapshot" / "repo",
            neon_binpath,
            pg_distrib_dir,
            pg_version,
            port_distributor,
            test_output_dir,
            pg_bin,
            request,
        )
    except Exception:
        if breaking_changes_allowed:
            pytest.xfail(
                "Breaking changes are allowed by ALLOW_BACKWARD_COMPATIBILITY_BREAKAGE env var"
            )
        else:
            raise

    assert (
        not breaking_changes_allowed
    ), "Breaking changes are allowed by ALLOW_BACKWARD_COMPATIBILITY_BREAKAGE, but the test has passed without any breakage"


@pytest.mark.xdist_group("compatibility")
@pytest.mark.order(after="test_create_snapshot")
def test_forward_compatibility(
    test_output_dir: Path,
    port_distributor: PortDistributor,
    pg_version: str,
    request: FixtureRequest,
):
    compatibility_neon_bin_env = os.environ.get("COMPATIBILITY_NEON_BIN")
    assert compatibility_neon_bin_env is not None, (
        "COMPATIBILITY_NEON_BIN is not set. It should be set to a path with Neon binaries "
        "(ideally generated by the previous version of Neon)"
    )
    compatibility_neon_bin = Path(compatibility_neon_bin_env).resolve()

    compatibility_postgres_distrib_dir_env = os.environ.get("COMPATIBILITY_POSTGRES_DISTRIB_DIR")
    assert (
        compatibility_postgres_distrib_dir_env is not None
    ), "COMPATIBILITY_POSTGRES_DISTRIB_DIR is not set. It should be set to a pg_install directrory (ideally generated by the previous version of Neon)"
    compatibility_postgres_distrib_dir = Path(compatibility_postgres_distrib_dir_env).resolve()

    compatibility_snapshot_dir = (
        test_output_dir.parent / "test_create_snapshot" / "compatibility_snapshot_pg14"
    )

    breaking_changes_allowed = (
        os.environ.get("ALLOW_FORWARD_COMPATIBILITY_BREAKAGE", "false").lower() == "true"
    )

    try:
        # Copy the snapshot to current directory, and prepare for the test
        prepare_snapshot(
            from_dir=compatibility_snapshot_dir,
            to_dir=test_output_dir / "compatibility_snapshot",
            port_distributor=port_distributor,
            neon_binpath=compatibility_neon_bin,
            pg_distrib_dir=compatibility_postgres_distrib_dir,
        )

        check_neon_works(
            test_output_dir / "compatibility_snapshot" / "repo",
            compatibility_neon_bin,
            compatibility_postgres_distrib_dir,
            pg_version,
            port_distributor,
            test_output_dir,
            PgBin(test_output_dir, compatibility_postgres_distrib_dir, pg_version),
            request,
        )
    except Exception:
        if breaking_changes_allowed:
            pytest.xfail(
                "Breaking changes are allowed by ALLOW_FORWARD_COMPATIBILITY_BREAKAGE env var"
            )
        else:
            raise

    assert (
        not breaking_changes_allowed
    ), "Breaking changes are allowed by ALLOW_FORWARD_COMPATIBILITY_BREAKAGE, but the test has passed without any breakage"


def prepare_snapshot(
    from_dir: Path,
    to_dir: Path,
    port_distributor: PortDistributor,
    neon_binpath: Path,
    pg_distrib_dir: Optional[Path] = None,
):
    assert from_dir.exists(), f"Snapshot '{from_dir}' doesn't exist"
    assert (from_dir / "repo").exists(), f"Snapshot '{from_dir}' doesn't contain a repo directory"
    assert (from_dir / "dump.sql").exists(), f"Snapshot '{from_dir}' doesn't contain a dump.sql"

    log.info(f"Copying snapshot from {from_dir} to {to_dir}")
    shutil.copytree(from_dir, to_dir)

    repo_dir = to_dir / "repo"

    # Remove old logs to avoid confusion in test artifacts
    for logfile in repo_dir.glob("**/*.log"):
        logfile.unlink()

    # Remove tenants data for compute
    for tenant in (repo_dir / "pgdatadirs" / "tenants").glob("*"):
        shutil.rmtree(tenant)

    # Remove wal-redo temp directory if it exists. Newer pageserver versions don't create
    # them anymore, but old versions did.
    for tenant in (repo_dir / "tenants").glob("*"):
        wal_redo_dir = tenant / "wal-redo-datadir.___temp"
        if wal_redo_dir.exists() and wal_redo_dir.is_dir():
            shutil.rmtree(wal_redo_dir)

    # Update paths and ports in config files
    pageserver_toml = repo_dir / "pageserver.toml"
    pageserver_config = toml.load(pageserver_toml)
    pageserver_config["remote_storage"]["local_path"] = str(repo_dir / "local_fs_remote_storage")
    pageserver_config["listen_http_addr"] = port_distributor.replace_with_new_port(
        pageserver_config["listen_http_addr"]
    )
    pageserver_config["listen_pg_addr"] = port_distributor.replace_with_new_port(
        pageserver_config["listen_pg_addr"]
    )
    # since storage_broker these are overriden by neon_local during pageserver
    # start; remove both to prevent unknown options during etcd ->
    # storage_broker migration. TODO: remove once broker is released
    pageserver_config.pop("broker_endpoint", None)
    pageserver_config.pop("broker_endpoints", None)
    etcd_broker_endpoints = [f"http://localhost:{port_distributor.get_port()}/"]
    if get_neon_version(neon_binpath) == "49da498f651b9f3a53b56c7c0697636d880ddfe0":
        pageserver_config["broker_endpoints"] = etcd_broker_endpoints  # old etcd version

    # Older pageserver versions had just one `auth_type` setting. Now there
    # are separate settings for pg and http ports. We don't use authentication
    # in compatibility tests so just remove authentication related settings.
    pageserver_config.pop("auth_type", None)
    pageserver_config.pop("pg_auth_type", None)
    pageserver_config.pop("http_auth_type", None)

    if pg_distrib_dir:
        pageserver_config["pg_distrib_dir"] = str(pg_distrib_dir)

    with pageserver_toml.open("w") as f:
        toml.dump(pageserver_config, f)

    snapshot_config_toml = repo_dir / "config"
    snapshot_config = toml.load(snapshot_config_toml)

    # Provide up/downgrade etcd <-> storage_broker to make forward/backward
    # compatibility test happy. TODO: leave only the new part once broker is released.
    if get_neon_version(neon_binpath) == "49da498f651b9f3a53b56c7c0697636d880ddfe0":
        # old etcd version
        snapshot_config["etcd_broker"] = {
            "etcd_binary_path": shutil.which("etcd"),
            "broker_endpoints": etcd_broker_endpoints,
        }
        snapshot_config.pop("broker", None)
    else:
        # new storage_broker version
        broker_listen_addr = f"127.0.0.1:{port_distributor.get_port()}"
        snapshot_config["broker"] = {"listen_addr": broker_listen_addr}
        snapshot_config.pop("etcd_broker", None)

    snapshot_config["pageserver"]["listen_http_addr"] = port_distributor.replace_with_new_port(
        snapshot_config["pageserver"]["listen_http_addr"]
    )
    snapshot_config["pageserver"]["listen_pg_addr"] = port_distributor.replace_with_new_port(
        snapshot_config["pageserver"]["listen_pg_addr"]
    )
    for sk in snapshot_config["safekeepers"]:
        sk["http_port"] = port_distributor.replace_with_new_port(sk["http_port"])
        sk["pg_port"] = port_distributor.replace_with_new_port(sk["pg_port"])

    if pg_distrib_dir:
        snapshot_config["pg_distrib_dir"] = str(pg_distrib_dir)

    with snapshot_config_toml.open("w") as f:
        toml.dump(snapshot_config, f)

    # Ensure that snapshot doesn't contain references to the original path
    rv = subprocess.run(
        [
            "grep",
            "--recursive",
            "--binary-file=without-match",
            "--files-with-matches",
            "test_create_snapshot/repo",
            str(repo_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert (
        rv.returncode != 0
    ), f"there're files referencing `test_create_snapshot/repo`, this path should be replaced with {repo_dir}:\n{rv.stdout}"


# get git SHA of neon binary
def get_neon_version(neon_binpath: Path):
    out = subprocess.check_output([neon_binpath / "neon_local", "--version"]).decode("utf-8")
    return out.split("git:", 1)[1].rstrip()


def check_neon_works(
    repo_dir: Path,
    neon_binpath: Path,
    pg_distrib_dir: Path,
    pg_version: str,
    port_distributor: PortDistributor,
    test_output_dir: Path,
    pg_bin: PgBin,
    request: FixtureRequest,
):
    snapshot_config_toml = repo_dir / "config"
    snapshot_config = toml.load(snapshot_config_toml)
    snapshot_config["neon_distrib_dir"] = str(neon_binpath)
    snapshot_config["postgres_distrib_dir"] = str(pg_distrib_dir)
    with (snapshot_config_toml).open("w") as f:
        toml.dump(snapshot_config, f)

    # TODO: replace with NeonEnvBuilder / NeonEnv
    config: Any = type("NeonEnvStub", (object,), {})
    config.rust_log_override = None
    config.repo_dir = repo_dir
    config.pg_version = pg_version
    config.initial_tenant = snapshot_config["default_tenant_id"]
    config.neon_binpath = neon_binpath
    config.pg_distrib_dir = pg_distrib_dir
    config.preserve_database_files = True

    cli = NeonCli(config)
    cli.raw_cli(["start"])
    request.addfinalizer(lambda: cli.raw_cli(["stop"]))

    pg_port = port_distributor.get_port()
    cli.pg_start("main", port=pg_port)
    request.addfinalizer(lambda: cli.pg_stop("main"))

    connstr = f"host=127.0.0.1 port={pg_port} user=cloud_admin dbname=postgres"
    pg_bin.run(["pg_dumpall", f"--dbname={connstr}", f"--file={test_output_dir / 'dump.sql'}"])
    initial_dump_differs = dump_differs(
        repo_dir.parent / "dump.sql",
        test_output_dir / "dump.sql",
        test_output_dir / "dump.filediff",
    )

    # Check that project can be recovered from WAL
    # loosely based on https://github.com/neondatabase/cloud/wiki/Recovery-from-WAL
    tenant_id = snapshot_config["default_tenant_id"]
    timeline_id = dict(snapshot_config["branch_name_mappings"]["main"])[tenant_id]
    pageserver_port = snapshot_config["pageserver"]["listen_http_addr"].split(":")[-1]
    auth_token = snapshot_config["pageserver"]["auth_token"]
    pageserver_http = PageserverHttpClient(
        port=pageserver_port,
        is_testing_enabled_or_skip=lambda: True,  # TODO: check if testing really enabled
        auth_token=auth_token,
    )

    shutil.rmtree(repo_dir / "local_fs_remote_storage")
    pageserver_http.timeline_delete(tenant_id, timeline_id)
    pageserver_http.timeline_create(tenant_id, timeline_id)
    pg_bin.run(
        ["pg_dumpall", f"--dbname={connstr}", f"--file={test_output_dir / 'dump-from-wal.sql'}"]
    )
    # The assert itself deferred to the end of the test
    # to allow us to perform checks that change data before failing
    dump_from_wal_differs = dump_differs(
        test_output_dir / "dump.sql",
        test_output_dir / "dump-from-wal.sql",
        test_output_dir / "dump-from-wal.filediff",
    )

    # Check that we can interract with the data
    pg_bin.run(["pgbench", "--time=10", "--progress=2", connstr])

    assert not dump_from_wal_differs, "dump from WAL differs"
    assert not initial_dump_differs, "initial dump differs"


def dump_differs(first: Path, second: Path, output: Path) -> bool:
    """
    Runs diff(1) command on two SQL dumps and write the output to the given output file.
    Returns True if the dumps differ, False otherwise.
    """

    with output.open("w") as stdout:
        rv = subprocess.run(
            [
                "diff",
                "--unified",  # Make diff output more readable
                "--ignore-matching-lines=^--",  # Ignore changes in comments
                "--ignore-blank-lines",
                str(first),
                str(second),
            ],
            stdout=stdout,
        )

    return rv.returncode != 0
