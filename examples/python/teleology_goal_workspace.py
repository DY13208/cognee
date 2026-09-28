"""Read a goal's local path, detail, and paged purpose relations.

Set COGNEE_API_URL, COGNEE_API_KEY, DATASET_ID, and GOAL_ID before running.
The example only reads data and never prints the API key.
"""

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def read_goal_resource(suffix: str, **params):
    base = os.environ["COGNEE_API_URL"].rstrip("/")
    goal_id = os.environ["GOAL_ID"]
    query = urlencode({"dataset_id": os.environ["DATASET_ID"], **params})
    request = Request(
        f"{base}/v1/teleology/annotations/goals/{goal_id}/{suffix}?{query}",
        headers={"X-Api-Key": os.environ["COGNEE_API_KEY"]},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


if __name__ == "__main__":
    path = read_goal_resource("path")
    detail = read_goal_resource("detail")
    relations = read_goal_resource("relations", relationship="serves", limit=30, offset=0)
    print(
        json.dumps(
            {
                "path": path["path"],
                "goal": detail["goal"],
                "serves_total": relations["total"],
                "serves_page": relations["items"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
