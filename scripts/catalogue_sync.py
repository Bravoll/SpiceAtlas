"""Build/resume the metadata catalogue without downloading article bodies or images."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from atlas.catalogue import catalogue
from atlas.discovery import jobs
from atlas.workspaces import workspaces

async def run(args):
    job=jobs.get(args.resume) if args.resume else jobs.create(args.kind,{"max_depth":args.depth,"max_categories":args.max_categories})
    if not job:raise SystemExit("Job not found")
    print("JOB",job["id"],job["kind"],flush=True)
    task=asyncio.create_task(jobs.run(job["id"]))
    while not task.done():
        await asyncio.wait([task],timeout=10)
        current=jobs.get(job["id"])
        print(json.dumps(jobs.public(current),ensure_ascii=False),flush=True)
    await task
    print("CATALOGUE",json.dumps(catalogue.stats()),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("kind",choices=["wiki","gbif"])
    parser.add_argument("--depth",type=int,default=2)
    parser.add_argument("--max-categories",type=int,default=200)
    parser.add_argument("--resume")
    with workspaces.use(workspaces.active_id):asyncio.run(run(parser.parse_args()))
