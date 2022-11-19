# Test sequential scan speed
#
from contextlib import closing

import pytest
from fixtures.benchmark_fixture import MetricReport
from fixtures.compare_fixtures import PgCompare
from fixtures.log_helper import log
from pytest_lazyfixture import lazy_fixture  # type: ignore


@pytest.mark.parametrize(
    "rows,iters,workers",
    [
        # The test table is large enough (3-4 MB) that it doesn't fit in the compute node
        # cache, so the seqscans go to the page server. But small enough that it fits
        # into memory in the page server.
        pytest.param(100000, 100, 0),
        # Also test with a larger table, with and without parallelism
        pytest.param(10000000, 1, 0),
        pytest.param(10000000, 1, 4),
    ],
)
@pytest.mark.parametrize(
    "env",
    [
        # Run on all envs
        pytest.param(lazy_fixture("neon_compare"), id="neon"),
        pytest.param(lazy_fixture("vanilla_compare"), id="vanilla"),
        pytest.param(lazy_fixture("remote_compare"), id="remote", marks=pytest.mark.remote_cluster),
    ],
)
def test_seqscans(env: PgCompare, rows: int, iters: int, workers: int):
    with closing(env.pg.connect()) as conn:
        with conn.cursor() as cur:
            cur.execute("drop table if exists t;")
            cur.execute("create table t (i integer);")
            cur.execute(f"insert into t values (generate_series(1,{rows}));")

            # Verify that the table is larger than shared_buffers
            cur.execute(
                """
            select setting::int * pg_size_bytes(unit) as shared_buffers, pg_relation_size('t') as tbl_ize
            from pg_settings where name = 'shared_buffers'
            """
            )
            row = cur.fetchone()
            assert row is not None
            shared_buffers = row[0]
            table_size = row[1]
            log.info(f"shared_buffers is {shared_buffers}, table size {table_size}")
            assert int(shared_buffers) < int(table_size)
            env.zenbenchmark.record("table_size", table_size, "bytes", MetricReport.TEST_PARAM)

            cur.execute(f"set max_parallel_workers_per_gather = {workers}")

            with env.record_duration("run"):
                for i in range(iters):
                    cur.execute("select count(*) from t;")
