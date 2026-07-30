"""
Example of OpenDMAFetcher recursing a folder hierarchy and fetching all documents.

Run the tutorial REST service docker container:
```
docker run -p 8080:8080 ghcr.io/opendma/tutorial-xmlrepo:0.8.1
```
It will provide the tutorial XML repository. Make sure that this service is available by opening
http://localhost:8080/opendma
in a web browser.
"""

from opendma_haystack import OpenDMAFetcher

fetcher = OpenDMAFetcher(
    endpoint="http://localhost:8080/opendma",
    username="ignored",
    password="ignored",
    repository_id="sample-repo",
    include_no_content=True,
)

print("recurse_folders=False")

result = fetcher.run(
    folder_ids=["sample-folder-root"],
    recurse_folders=False,
)
streams = result["streams"]
print(f"Fetched {len(streams)} streams")

for stream in streams:
    print(f"ID: {stream.meta.get('opendma_id')}, bytes: {len(stream.data)}")

print("\nrecurse_folders=True")

result = fetcher.run(
    folder_ids=["sample-folder-root"],
    recurse_folders=True,
)
streams = result["streams"]
print(f"Fetched {len(streams)} streams")

for stream in streams:
    print(f"ID: {stream.meta.get('opendma_id')}, bytes: {len(stream.data)}")
