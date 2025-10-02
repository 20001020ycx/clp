from typing import List, Dict
import asyncio

from pymongo.asynchronous.mongo_client import AsyncMongoClient
import aiomysql
import msgpack

from constants import *
from settings import *


class CLPConnector:

    def __init__(self):
        mongo_url = f'mongodb://{CLP_RESULTS_CACHE_SERVICE_NAME}:{CLP_RESULTS_CACHE_PORT}/'
        self.mongo_client = AsyncMongoClient(mongo_url)
        self.results_cache = self.mongo_client[CLP_RESULTS_CACHE_CLP_DB_NAME]

        # Configuration to be used in `aiomysql.connect` to MariaDB.
        self.db_conf = {
            'host': CLP_DB_SERVICE_NAME,
            'port': CLP_DB_PORT,
            'user': CLP_DB_USER,
            'password': CLP_DB_PASS,
            'db': CLP_DB_NAME,
        }


    async def submit_query(self, query: str, begin_ts: int, end_ts: int) -> str:
        """
        Submits a query to the CLP database and returns the ID of the query.

        Args:
            query: the query string
            begin_ts: the beginning timestamp of the query range
            end_ts: the end timestamp of the query range

        Raises:
            ValueError: when end_ts is smaller than begin_ts
            aiomysql.Error: if there is an error connecting to or querying MariaDB
            pymongo.errors.PyMongoError: if there is an error connecting to or writing to MongoDB
            Exception: for any other unexpected errors

        Returns:
            query_id: the ID assigned to the query
        """
        if end_ts < begin_ts:
            raise ValueError('end_ts must be greater than or equal to begin_ts.')

        job_config = msgpack.packb({
            'begin_timestamp': begin_ts,
            'dataset': None,
            'end_timestamp': end_ts,
            'ignore_case': True,
            'max_num_results': SEARCH_MAX_NUM_RESULTS,
            'query_string': query,
        })

        async with aiomysql.connect(**self.db_conf) as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO query_jobs (type, job_config) VALUES (%s, %s);",
                                  (int(QueryJobType.SEARCH_OR_AGGREGATION), job_config))
                await conn.commit()
                await cur.execute("SELECT LAST_INSERT_ID();")
                result = await cur.fetchone()
                query_id = result[0] if result else None
                print('query_id is ', query_id)

        # Create a collection in MongoDB where the name is the last_insert_id
        if query_id is not None:
            await self.results_cache.create_collection(str(query_id))
            print('created collection ', str(query_id))

        results_metadata_doc = {
            "_id": str(query_id),
            "errorMsg": None,
            "errorName": None,
            "lastSignal": "resp-querying",
            "queryEngine": "clp",
        }
        await self.results_cache["results-metadata"].insert_one(results_metadata_doc)
        print('inserted results-metadata doc for ', str(query_id))

        return query_id


    async def read_job_status(self, query_id: str) -> int:
        """
        Reads the job status of a query.

        Raises:
            aiomysql.Error: if there is an error connecting to or querying MariaDB
            ValueError: when the query is not found

        Args:
            query_id: the ID of the query
        """
        async with aiomysql.connect(**self.db_conf) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT status FROM query_jobs WHERE id = %s;", (query_id,))
                result = await cur.fetchone()
                status = result[0] if result else None

        if status is None:
            raise ValueError(f'Query job with ID {query_id} not found.')

        return status


    async def wait_query_completion(self, query_id: str):
        """
        Waits for the query to complete.

        Args:
            query_id: the ID of the query

        Raises:
            aiomysql.Error: if there is an error connecting to or querying MariaDB
            ValueError: when the query is not found
            RuntimeError: when the query fails or is cancelled

        Returns:
            status: the status of the query
        """
        WAITING_STATES = {
            QueryJobStatus.PENDING,
            QueryJobStatus.RUNNING,
            QueryJobStatus.CANCELLING
        }

        while True:
            status = await self.read_job_status(query_id)
            if status in WAITING_STATES:
                await asyncio.sleep(POLLING_INTERVAL_SECONDS)
            elif status == QueryJobStatus.SUCCEEDED:
                break
            elif status == QueryJobStatus.FAILED:
                raise RuntimeError(f'Query job with ID {query_id} failed.')
            elif status == QueryJobStatus.CANCELLED:
                raise RuntimeError(f'Query job with ID {query_id} was cancelled.')
            elif status == QueryJobStatus.KILLED:
                raise RuntimeError(f'Query job with ID {query_id} was killed.')
            else:
                raise RuntimeError(f'Query job with ID {query_id} has unknown status {status}.')


    async def read_results(self, query_id: str) -> List[Dict]:
        """
        Reads the results of a query.

        Args:
            query_id: the ID of the query

        Returns:
            results: a list of messages
        """
        collection = self.results_cache[str(query_id)]
        results = []

        async for doc in collection.find({}):
            results.append(doc)

        return results
