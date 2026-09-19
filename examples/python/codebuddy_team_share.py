"""Share one Cognee dataset with an already registered WorkBuddy colleague.

Set COGNEE_API_URL to the HTTPS API base (including /backend for the local proxy),
COGNEE_API_KEY to an API key created by the dataset owner, DATASET_ID and MEMBER_ID.
MEMBER_ID is the colleague's Cognee UUID from /api/v1/auth/codebuddy/me, not their
provider subject. This grants read access only and does not copy the graph.
"""

import asyncio
import os
from uuid import UUID

import httpx


async def main():
    api_url = os.environ["COGNEE_API_URL"].rstrip("/")
    dataset_id = str(UUID(os.environ["DATASET_ID"]))
    member_id = str(UUID(os.environ["MEMBER_ID"]))
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{api_url}/api/v1/permissions/datasets/{member_id}",
            params={"permission_name": "read"},
            headers={"X-Api-Key": os.environ["COGNEE_API_KEY"]},
            json=[dataset_id],
        )
        response.raise_for_status()
    print("Read access granted. The colleague can now select the same dataset.")


if __name__ == "__main__":
    asyncio.run(main())
