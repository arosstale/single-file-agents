#!/usr/bin/env python3

# /// script
# dependencies = [
#   "google-genai>=1.1.0",
#   "rich>=13.7.0",
# ]
# ///

"""
/// Example Usage

# Run DuckDB agent with default compute loops (3)
uv run sfa_duckdb_gemini_v2.py -d ./data/mock.db -p "Show me all users with score above 80"

# Run with custom compute loops
uv run sfa_duckdb_gemini_v2.py -d ./data/mock.db -p "Show me all users with score above 80" -c 5

///
"""

import os
import sys
import json
import argparse
import subprocess
from typing import List
from rich.console import Console
from rich.panel import Panel
from google import genai
from google.genai import types

# Initialize rich console
console = Console()


def list_tables(reasoning: str) -> List[str]:
    """Returns a list of tables in the database.

    The agent uses this to discover available tables and make informed decisions.

    Args:
        reasoning: Explanation of why we're listing tables relative to user request

    Returns:
        List of table names as strings
    """
    try:
        result = subprocess.run(
            f"duckdb {DB_PATH} -c \"SELECT name FROM sqlite_master WHERE type='table';\"",
            shell=True,
            text=True,
            capture_output=True,
        )
        console.log(f"[blue]List Tables Tool[/blue] - Reasoning: {reasoning}")
        return result.stdout.strip().split("\n")
    except Exception as e:
        console.log(f"[red]Error listing tables: {str(e)}[/red]")
        return []


def describe_table(reasoning: str, table_name: str) -> str:
    """Returns schema information about the specified table.

    The agent uses this to understand table structure and available columns.

    Args:
        reasoning: Explanation of why we're describing this table
        table_name: Name of table to describe

    Returns:
        String containing table schema information
    """
    try:
        result = subprocess.run(
            f'duckdb {DB_PATH} -c "DESCRIBE {table_name};"',
            shell=True,
            text=True,
            capture_output=True,
        )
        console.log(
            f"[blue]Describe Table Tool[/blue] - Table: {table_name} - Reasoning: {reasoning}"
        )
        return result.stdout
    except Exception as e:
        console.log(f"[red]Error describing table: {str(e)}[/red]")
        return ""


def sample_table(reasoning: str, table_name: str, row_count: int) -> str:
    """Returns a sample of rows from the specified table.

    The agent uses this to understand actual data content and patterns.

    Args:
        reasoning: Explanation of why we're sampling this table
        table_name: Name of table to sample from
        row_count: Number of rows to sample (aim for 3-5 rows)

    Returns:
        String containing sample rows in readable format
    """
    try:
        result = subprocess.run(
            f'duckdb {DB_PATH} -c "SELECT * FROM {table_name} LIMIT {row_count};"',
            shell=True,
            text=True,
            capture_output=True,
        )
        console.log(
            f"[blue]Sample Table Tool[/blue] - Table: {table_name} - Rows: {row_count} - Reasoning: {reasoning}"
        )
        return result.stdout
    except Exception as e:
        console.log(f"[red]Error sampling table: {str(e)}[/red]")
        return ""


def run_test_sql_query(reasoning: str, sql_query: str) -> str:
    """Executes a test SQL query and returns results.

    The agent uses this to validate queries before finalizing them.
    Results are only shown to the agent, not the user.

    Args:
        reasoning: Explanation of why we're running this test query
        sql_query: The SQL query to test

    Returns:
        Query results as a string
    """
    try:
        result = subprocess.run(
            f'duckdb {DB_PATH} -c "{sql_query}"',
            shell=True,
            text=True,
            capture_output=True,
        )
        console.log(f"[blue]Test Query Tool[/blue] - Reasoning: {reasoning}")
        console.log(f"[dim]Query: {sql_query}[/dim]")
        return result.stdout
    except Exception as e:
        console.log(f"[red]Error running test query: {str(e)}[/red]")
        return str(e)


def run_final_sql_query(reasoning: str, sql_query: str) -> str:
    """Executes the final SQL query and returns results to user.

    This is the last tool call the agent should make after validating the query.

    Args:
        reasoning: Final explanation of how this query satisfies user request
        sql_query: The validated SQL query to run

    Returns:
        Query results as a string
    """
    try:
        result = subprocess.run(
            f'duckdb {DB_PATH} -c "{sql_query}"',
            shell=True,
            text=True,
            capture_output=True,
        )
        console.log(
            Panel(
                f"[green]Final Query Tool[/green]\nReasoning: {reasoning}\nQuery: {sql_query}"
            )
        )
        return result.stdout
    except Exception as e:
        console.log(f"[red]Error running final query: {str(e)}[/red]")
        return str(e)


AGENT_PROMPT = """<purpose>
    You are a world-class expert at crafting precise DuckDB SQL queries.
    Your goal is to generate accurate queries that exactly match the user's data needs.
</purpose>

<instructions>
    <instruction>Use the provided tools to explore the database and construct the perfect query.</instruction>
    <instruction>Start by listing tables to understand what's available.</instruction>
    <instruction>Describe tables to understand their schema and columns.</instruction>
    <instruction>Sample tables to see actual data patterns.</instruction>
    <instruction>Test queries before finalizing them.</instruction>
    <instruction>Only call run_final_sql_query when you're confident the query is perfect.</instruction>
    <instruction>Be thorough but efficient with tool usage.</instruction>
    <instruction>Think step by step about what information you need.</instruction>
</instructions>

<tools>
    <tool>
        <name>list_tables</name>
        <description>Returns list of available tables in database</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we need to list tables relative to user request</description>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>describe_table</name>
        <description>Returns schema info for specified table</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we need to describe this table</description>
            </parameter>
            <parameter>
                <name>table_name</name>
                <type>string</type>
                <description>Name of table to describe</description>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>sample_table</name>
        <description>Returns sample rows from specified table</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we need to sample this table</description>
            </parameter>
            <parameter>
                <name>table_name</name>
                <type>string</type>
                <description>Name of table to sample</description>
            </parameter>
            <parameter>
                <name>row_count</name>
                <type>integer</type>
                <description>Number of rows to sample aim for 3-5 rows</description>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>run_test_sql_query</name>
        <description>Tests a SQL query and returns results (only visible to agent)</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Why we're testing this specific query</description>
            </parameter>
            <parameter>
                <name>sql_query</name>
                <type>string</type>
                <description>The SQL query to test</description>
            </parameter>
        </parameters>
    </tool>
    
    <tool>
        <name>run_final_sql_query</name>
        <description>Runs the final validated SQL query and shows results to user</description>
        <parameters>
            <parameter>
                <name>reasoning</name>
                <type>string</type>
                <description>Final explanation of how query satisfies user request</description>
            </parameter>
            <parameter>
                <name>sql_query</name>
                <type>string</type>
                <description>The validated SQL query to run</description>
            </parameter>
        </parameters>
    </tool>
</tools>

<user-request>
    {{user_request}}
</user-request>
"""


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="DuckDB Agent using Gemini API")
    parser.add_argument(
        "-d", "--db", required=True, help="Path to DuckDB database file"
    )
    parser.add_argument("-p", "--prompt", required=True, help="The user's request")
    parser.add_argument(
        "-c",
        "--compute",
        type=int,
        default=3,
        help="Maximum number of agent loops (default: 3)",
    )
    args = parser.parse_args()

    # Configure the API key
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        console.print(
            "[red]Error: GEMINI_API_KEY environment variable is not set[/red]"
        )
        console.print(
            "Please get your API key from https://aistudio.google.com/app/apikey"
        )
        console.print("Then set it with: export GEMINI_API_KEY='your-api-key-here'")
        sys.exit(1)

    # Set global DB_PATH for tool functions
    global DB_PATH
    DB_PATH = args.db

    # Initialize Gemini client
    client = genai.Client(api_key=GEMINI_API_KEY)

    completed_prompt = AGENT_PROMPT.replace("{{user_request}}", args.prompt)

    # Initialize message history
    messages = [
        {
            "role": "user",
            "content": completed_prompt,
        }
    ]

    # Main agent loop
    for i in range(args.compute):
        console.rule(f"[yellow]Agent Loop {i+1}/{args.compute}[/yellow]")

        try:
            # Generate content with tool support
            response = client.models.generate_content(
                model="gemini-2.0-flash-001",
                contents=[
                    *messages,
                ],
                config=types.GenerateContentConfig(
                    tools=[
                        list_tables,
                        describe_table,
                        sample_table,
                        run_test_sql_query,
                        run_final_sql_query,
                    ],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="ANY")
                    ),
                ),
            )

            # Process tool calls
            if response.function_calls:
                for func_call in response.function_calls:
                    # Extract function name and args
                    func_name = func_call.name
                    func_args = func_call.args

                    console.print(f"[blue]Function Call:[/blue] {func_name}")
                    console.print(f"[dim]Args: {func_args}[/dim]")

                    try:
                        # Call appropriate function
                        if func_name == "list_tables":
                            result = list_tables(**func_args)
                        elif func_name == "describe_table":
                            result = describe_table(**func_args)
                        elif func_name == "sample_table":
                            result = sample_table(**func_args)
                        elif func_name == "run_test_sql_query":
                            result = run_test_sql_query(**func_args)
                        elif func_name == "run_final_sql_query":
                            result = run_final_sql_query(**func_args)
                            console.print("\n[green]Final Results:[/green]")
                            console.print(result)
                            return  # Exit after final query

                        # Add successful result to messages
                        messages.append(
                            {
                                "role": "function",
                                "name": func_name,
                                "content": str(result),
                            }
                        )
                    except Exception as e:
                        # Add error message for failed function call
                        error_msg = f"Error executing {func_name} with args {func_args}. Try again: {str(e)}"

                        messages.append({"role": "model", "content": error_msg})

                        console.print(f"[red]{error_msg}[/red]")
                        continue

            else:
                # Add model response to messages
                messages.append({"role": "model", "content": response.text})

        except Exception as e:
            console.print(f"[red]Error in agent loop: {str(e)}[/red]")
            raise e
            sys.exit(1)

    console.print(
        "[yellow]Warning: Reached maximum compute loops without final query[/yellow]"
    )


if __name__ == "__main__":
    main()
