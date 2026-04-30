"""
Use this to help debug using django shell
The function returns the total time and the number of queries
"""

from django.db import connection, reset_queries


def query_result():
    list_queries = [float(query["time"]) for query in connection.queries]
    reset_queries()

    return {"time": sum(list_queries), "len": len(list_queries)}
