"""MCP Server implementation."""

from typing import Any

from fastmcp import Context, FastMCP
from types import SimpleNamespace
from clp_mcp_server.clp_connector import ClpConnector

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from . import constants
from .session_manager import SessionManager




def create_mcp_server() -> FastMCP:
    """
    Creates and defines API tool calls for the CLP MCP server.

    :return: A configured `FastMCP` instance.
    :raise: Propagates `FastMCP.__init__`'s exceptions.
    :raise: Propagates `FastMCP.tool`'s exceptions.
    """
    mcp = FastMCP(name=constants.SERVER_NAME)

    session_manager = SessionManager(constants.SESSION_TTL_MINUTES)

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(_request: Request) -> PlainTextResponse:
        """
        Health check endpoint.
        :param _request: An HTTP request object.
        :return: A JSON response indicating server is healthy.
        """
        return PlainTextResponse("OK")

    @mcp.tool
    def get_instructions(ctx: Context) -> str:
        """
        Gets a pre-defined “system prompt” that guides the LLM behavior.
        This function must be invoked before any other `FastMCP.tool`.

        :param ctx: The `FastMCP` context containing the metadata of the underlying MCP session.
        :return: A string of “system prompt”.
        """
        session = session_manager.get_or_create_session(ctx.session_id)
        session.is_instructions_retrieved = True
        return constants.SYSTEM_PROMPT

    @mcp.tool
    def get_nth_page(page_index: int, ctx: Context) -> dict[str, Any]:
        """
        Retrieves the n-th page of a paginated response with the paging metadata from the previous
        query.

        :param page_index: Zero-based index, e.g., 0 for the first page.
        :param ctx: The `FastMCP` context containing the metadata of the underlying MCP session.
        :return: Dictionary containing paged log entries and the paging metadata if the
        page `page_index` can be retrieved.
        :return: Dictionary with ``{"Error": "error message describing the failure"}`` if fails to
        retrieve page `page_index`.
        """
        return session_manager.get_nth_page(ctx.session_id, page_index)

    @mcp.tool
    async def search_kql_query(kql_query: str, ctx: Context) -> dict[str, object]:
        """
        Searches the logs for the specified query and returns the latest 10 log messages matching
        the query, i.e. the first page of the complete results.

        :param kql_query:
        :param ctx: The `FastMCP` context containing the metadata of the underlying MCP session.
        :return: Forwards `FastMCP.tool`''s `get_nth_page`'s return values on success:
        :return: A dictionary with the following key-value pair on failures:
            - "Error": An error status indicating the reason of the query failure.
        """
        clp_config = SimpleNamespace(
            results_cache=SimpleNamespace(host="results-cache", port=27017, db_name="clp-query-results"),
            database=SimpleNamespace(host="database", port=3306, name="clp-db"),
        )
        connector = ClpConnector(clp_config)
        queryID = await connector.submit_query(kql_query, 1, 1756309092954)
        print(queryID)
        await connector.wait_query_completion(queryID)
        print("Query completed")
        results = await connector.read_results(queryID)
        print(results)
        cleaned_obj = [{k: v for k, v in obj.items() if k != '_id'} for obj in results]
        return {"queryID": queryID, "results": cleaned_obj }


    # @mcp.tool
    # def search_kql_query_with_timestamp(kql_query: str, begin_timestamp: datetime, end_timestamp: datetime, ctx: Context) -> dict[str, object]:
    #     """Search the logs for the specified query and returns the latest 10 log messages
    #     matching the query (first page of results) and the total number of pages available

    #     Args:
    #      kql_query: KQL (Kabana Query Language) query to find matching log messages 
    #      begin_timestamp: Log messages with timestamp before begin_timestamp will not be matched
    #      end_timestamp: Log messages with timestamp after end_timestamp will not be matched.

    #     Returns:
    #      Page0: The latest 10 log messages matching the query and timestamp range
    #      NumPages: Total number of pages that can be indexed
    #     """

    #     num_pages = 0
    #     log_page_0 = [""]
    #     return {"Page0": log_page_0, "NumPages": num_pages}

    @mcp.tool
    def hello_world(name: str = "clp-mcp-server user") -> dict[str, Any]:
        """
        Provides a simple hello world greeting.

        :param name:
        :return: A greeting message to the given `name`.
        """
        return {
            "message": f"Hello World, {name.strip()}!",
            "server": constants.SERVER_NAME,
            "status": "running",
        }

    return mcp
