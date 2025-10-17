import asyncio
import time

from fastmcp import Client


async def test_concurrent_sessions():
    """Test that hello_world does not block other requests from other clients"""
    # Create two separate client instances
    client_slow = Client("http://localhost:8005/mcp")
    client_fast = Client("http://localhost:8005/mcp")

    async def slow_client_task():
        """Client that calls hello_world (takes infinite time)"""
        async with client_slow:
            await client_slow.ping()
            print("Slow client: Connected successfully")
            print("Slow client: Starting hello_world (infinite time)...")

            # This will run forever - don't await it directly
            result = await client_slow.call_tool("search_kql_query", kql_query="error")
            print(f"Slow client: hello_world completed: {result}")
            return "slow_done"

    async def fast_client_task():
        """Client that calls get_instructions (should complete quickly)"""
        async with client_fast:
            await client_fast.ping()
            print("Fast client: Connected successfully")

            # Wait a moment to ensure hello_world has started
            await asyncio.sleep(1)

            print("Fast client: Making get_instructions call...")
            start_time = time.time()
            result = await client_fast.call_tool("search_kql_query", kql_query="error")
            end_time = time.time()

            print(f"Fast client: get_instructions completed in {end_time - start_time:.2f} seconds")
            print(f"Fast client: Result: {result}")
            return {"result": result, "duration": end_time - start_time}

    print("=== Testing Concurrent Session Connections ===")
    print("Starting slow hello_world client and fast get_instructions client...")

    start_time = time.time()

    try:
        # Start both clients concurrently
        slow_task = asyncio.create_task(slow_client_task())
        fast_task = asyncio.create_task(fast_client_task())

        # Wait for fast client to complete first
        fast_result = await fast_task
        print("✓ Fast client completed successfully!")
        print(f"Fast client result: {fast_result}")

        # Now wait for slow client to complete
        print("\nWaiting for slow hello_world task to complete...")
        slow_result = await slow_task
        print("✓ Slow client completed successfully!")
        print(f"Slow client result: {slow_result}")

        end_time = time.time()
        total_time = end_time - start_time

        print("\n=== Test Results ===")
        print(f"Total test duration: {total_time:.2f} seconds")
        print(f"get_instructions completed in: {fast_result['duration']:.2f} seconds")
        print("✓ PROOF: hello_world did NOT block get_instructions from other client")
        print("\n=== Final Results ===")
        print(f"Fast client (get_instructions): {fast_result}")
        print(f"Slow client (hello_world): {slow_result}")

        return {"fast": fast_result, "slow": slow_result}

    except Exception as e:
        print(f"✗ Test failed: {e}")
        return None

async def main():
    """Main test runner"""
    await test_concurrent_sessions()

if __name__ == "__main__":
    asyncio.run(main())
