"""Operator-invoked, one-shot sync; never auto-selects all projects."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from .connector import DirectoryConnector, DirectoryReplica, register_source
from .contract import digest, proof_digest
from .transport import DirectoryRPC


async def run(args):
    proof = os.environ["CODE_PLATFORM_SYNC_SOURCE_PROOF"]
    proof_digest(proof)
    from jiuwenswarm.common.utils import get_user_workspace_dir
    async with DirectoryRPC(args.url, os.environ["CODE_PLATFORM_SYNC_ACCOUNT_TOKEN"], ca_file=args.ca_file) as rpc:
        # This installation receives replicas. Cloud publishing stays on Gateway.
        source = await register_source(rpc.request, args.installation_id, proof)
        namespace = [args.url, source["id"], source["generation"]]
        # Use the original data-root helper; the index is not a second project store.
        root = Path(get_user_workspace_dir()).resolve() / "data-sync" / digest(namespace)
        replica = DirectoryReplica(root, namespace)
        connector = DirectoryConnector(rpc.request, source, proof, replica)
        if not args.receive_only:
            if args.kind == "cloud":
                await connector.publish_cloud(args.project or [])
            else:
                await connector.publish(args.project or [])
        rows = await connector.pull()
        print(json.dumps({"source_id": source["id"], "projects": len(rows), "status": replica.get("status"),
                          "watermark": replica.get("watermark"), "account_complete": False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="original Gateway wss://host/ws endpoint")
    parser.add_argument("--installation-id", required=True, help="stable operator-assigned local installation ID")
    parser.add_argument("--kind", choices=["local", "cloud"], default="local")
    parser.add_argument("--ca-file", help="optional trusted private CA bundle")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--project", action="append", help="explicit original project ID; repeat to select several")
    selection.add_argument("--withdraw-all", action="store_true", help="withdraw this source's metadata only")
    selection.add_argument("--receive-only", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        # Do not echo transport errors, URLs or credentials into operator logs.
        parser.exit(1, "directory sync failed: " + (getattr(exc, "code", None) or type(exc).__name__) + "\n")


if __name__ == "__main__":
    main()
