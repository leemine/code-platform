---
id: B_20261101_2056_missing-lfs-demo-videos
title: Remove unavailable LFS demo video references
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [docs]
files: [.gitattributes, README.md, docs/assets/videos, docs/en/ChinaChannels.md, docs/en/TaskPlanning.md, docs/zh/国内频道.md, docs/zh/任务规划.md]
designs: []
design_note: User-approved documentation asset cleanup; no independent architecture design.
---

# Missing LFS demo video cleanup

## Cause and scope

At base 9acd92c5c81aa99ef5e616601313f16289cdbd78, six documentation MP4 files contain only valid Git LFS pointers. Authenticated GitHub LFS batch-download metadata reports object-not-found (404) for all six in both leemine/code-platform and leemine/codeswarm. The six referenced objects total 96,310,970 bytes; none is present in the inspected local LFS caches. The official GitHub develop branch also contains the six pointers, and its LFS metadata likewise reports 404. Five videos trace to official commit e5da656060ad6723ecd4b8e14eff60afd0271d88 (2026-03-19); the introduction video traces to 7062a05a514d6ef261100ece5a51ae5d307fdf9d (2026-08-07), followed by a filename correction. The pointers were inherited, rather than added for a local runtime feature. The exact cause of missing upstream LFS content is not established; the fork migration failed to detect this existing asset-availability issue.

The user approved deleting the unavailable demonstrations and their links. Delete only these six pointer files and the MP4 LFS attribute; preserve the browser runtime line-ending rule. Remove five dead video links from README and English/Chinese docs, retaining feature and channel instructions. The channel introduction now describes the written setup steps. No runtime, dependency, build, model or provider changes.

## Validation

The task checks candidate files independently against the base tree: six deletions are LFS pointers, no dangling local references target the removed videos, no remaining LFS pointers exist in candidate tracked files, no MP4 filter remains, and unrelated attributes and functional prose are retained. Inspect the exact diff and verify both main checkouts remain unchanged. Final results are recorded in the management repository's LFS-VIDEO-01 task and verification record.

Local validation does not run model, desktop, platform-build or stable suites for this documentation-only cleanup; PR CI outcomes are recorded separately in the management verification record. This does not repair old commits or frozen validation trees. No Git history rewrite is performed. The user subsequently authorized separate commits, pushes and PRs for both repositories; merge remains subject to the applicable checks.

## Retained limitation

Historical commits still reference missing LFS objects. This cleanup removes their references only from the candidate branch. Any future restored video must include actual content and verified object availability before adding a link. No new global upload gate or runtime restriction is introduced.
