import sys
from pathlib import Path

import pytest

sys.path.insert(0, str((Path(__file__).parent.parent).resolve()))
import clp_connector


@pytest.mark.asyncio
async def test_submit_query():
    connector = clp_connector.CLPConnector()
    await connector.submit_query('1', 0, 1790790051822)

@pytest.mark.asyncio
async def test_read_job_status():
    connector = clp_connector.CLPConnector()
    status = await connector.read_job_status('12')
    print('job status: ', status)

@pytest.mark.asyncio
async def test_wait_query_completion():
    connector = clp_connector.CLPConnector()
    await connector.wait_query_completion('12')

@pytest.mark.asyncio
async def test_read_results():
    connector = clp_connector.CLPConnector()
    results = await connector.read_results('12')
    print(results[:3])
