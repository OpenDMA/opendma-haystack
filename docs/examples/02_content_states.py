"""
Example demonstrating OpenDMAFetcher handling for documents with and without content.

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

result = fetcher.run(targets=["hello-world-document", "sample-no-content-document"])
streams = result["streams"]

print(f"Fetched {len(streams)} streams")

for stream in streams:
    print(f"ID: {stream.meta.get('opendma_id')}")
    print(f"Title: {stream.meta.get('opendma:Title')}")
    print(f"MIME type: {stream.mime_type}")
    print(f"Bytes available: {len(stream.data)}")
    print("Metadata:")
    for key, value in stream.meta.items():
        value_str = str(value)
        if len(value_str) > 100:
            value_str = value_str[:97] + "..."
        print(f"  {key}: {value_str}")
    print(f"{'-' * 80}")
