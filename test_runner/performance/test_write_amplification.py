# Demonstrate Write Amplification with naive oldest-first layer checkpointing
# algorithm.
#
# In each iteration of the test, we create a new table that's slightly under 10
# MB in size (10 MB is the current "segment size" used by the page server). Then
# we make a tiny update to all the tables already created. This creates a WAL
# pattern where you have a lot of updates on one segment (the newly created
# one), alternating with a small updates on all relations. This is the worst
# case scenario for the naive checkpointing policy where we write out the layers
# in LSN order, writing the oldest layer first. That creates a new 10 MB image
# layer to be created for each of those small updates.  This is the Write
# Amplification problem at its finest.
import os
from contextlib import closing
from fixtures.zenith_fixtures import PostgresFactory, ZenithPageserver

pytest_plugins = ("fixtures.zenith_fixtures", "fixtures.benchmark_fixture")

def test_write_amplification(postgres: PostgresFactory, pageserver: ZenithPageserver, pg_bin, zenith_cli, zenbenchmark, repo_dir: str):
    # Create a branch for us
    zenith_cli.run(["branch", "test_write_amplification", "empty"])

    pg = postgres.create_start('test_write_amplification')
    print("postgres is running on 'test_write_amplification' branch")

    # Open a connection directly to the page server that we'll use to force
    # flushing the layers to disk
    psconn = pageserver.connect();
    pscur = psconn.cursor()

    with closing(pg.connect()) as conn:
        with conn.cursor() as cur:
            # Get the timeline ID of our branch. We need it for the 'do_gc' command
            cur.execute("SHOW zenith.zenith_timeline")
            timeline = cur.fetchone()[0]

            with zenbenchmark.record_pageserver_writes(pageserver, 'pageserver_writes'):
                with zenbenchmark.record_duration('run'):

                    # NOTE: Because each iteration updates every table already created,
                    # the runtime and write amplification is O(n^2), where n is the
                    # number of iterations.
                    for i in range(25):
                        cur.execute(f'''
                        CREATE TABLE tbl{i} AS
                            SELECT g as i, 'long string to consume some space' || g as t
                            FROM generate_series(1, 100000) g
                        ''')
                        cur.execute(f"create index on tbl{i} (i);")
                        for j in range(1, i):
                            cur.execute(f"delete from tbl{j} where i = {i}")

                        # Force checkpointing. As of this writing, we don't have
                        # a back-pressure mechanism, and the page server cannot
                        # keep up digesting and checkpointing the WAL at the
                        # rate that it is generated. If we don't force a
                        # checkpoint, the WAL will just accumulate in memory
                        # until you hit OOM error. So in effect, we use much
                        # more memory to hold the incoming WAL, and write them
                        # out in larger batches than we'd really want. Using
                        # more memory hides the write amplification problem this
                        # test tries to demonstrate.
                        #
                        # The write amplification problem is real, and using
                        # more memory isn't the right solution. We could
                        # demonstrate the effect also by generating the WAL
                        # slower, adding some delays in this loop.  But forcing
                        # the the checkpointing and GC makes the test go faster,
                        # with the same total I/O effect.
                        pscur.execute(f"do_gc {pageserver.initial_tenant} {timeline} 0")

            # Report disk space used by the repository
            timeline_size = zenbenchmark.get_timeline_size(repo_dir, pageserver.initial_tenant, timeline)
            zenbenchmark.record('size', timeline_size / (1024*1024), 'MB')
