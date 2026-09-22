<div align="right">

**English** | [简体中文](README.zh-CN.md)

</div>

# Ruwen Writing System · 如文写作系统

**A structured AI writing system for long-form fiction: from story design and project knowledge to isolated chapter production, review, and canonical memory.**

Ruwen decomposes long-form fiction into work stages with explicit responsibilities, verifiable boundaries, and recoverable state. It treats text generation as one part of a larger system that also manages story development, external knowledge, project voice, chapter situations, isolated drafting, multi-role review, user approval, and long-term memory.

## What it contains

### Core writing system

The main plugin provides two public entry points:

- **如文·故事构思** — initializes and extends a fiction project, integrates external knowledge and literary references, develops characters and worlds, and compiles approved ideas into chapter situations.
- **如文·章节写作** — writes from an approved chapter situation in an isolated context, then coordinates first reading, editing, plot and reality checks, user approval, and canonical memory updates.

The separation is intentional: planning records, correction history, and validators should guide the work without leaking into the prose itself.

### Supporting components

| Component | Role | Relationship to the core |
| --- | --- | --- |
| [`Project Commercial Advisor`](02-项目商业顾问/project-commercial-advisor/) | Uses platform evidence, project economics, and operating results to support start / continue / adjust / stop decisions | Maintained inside this repository, but not a third writing entry and not part of chapter production |
| [`Web Fiction Genre Editor`](06-网文体裁编辑器/web-fiction-genre-editor/) | Edits an author's pre-approval draft for genre-specific reading experience | Version-pinned as an independent submodule; edited work still returns to the original approval flow |
| [`Ruwen Project Reader`](07-项目阅读器/ruwen-project-reader/) | Reads and summarizes a Ruwen project without changing its canon | A separate read-only support tool |

## Project case study

- [中文案例：把“一次性生成”变成“可持续创作”](docs/portfolio/ruwen-case-study.zh-CN.md)
- [Novel style chapter reader](https://hunterhigh.github.io/ruwen-writing-system/): *Eastern Warring States*, chapter 55 (Pei Jingxing edition), and *Wenfengtai*.
- [Eastern Warring States novel project](projects/东方战国/): the complete project snapshot from August 13, 2026.

## Repository structure

```text
01-完整插件/              Ruwen core plugin
02-项目商业顾问/          Integrated commercial decision component
03-设计与迁移/            Architecture and migration records
04-校验记录/              Frozen hashes and validation reports
05-行为验证/              Behavioral validation material
06-网文体裁编辑器/        Independently versioned editing submodule
07-项目阅读器/            Read-only project reader
docs/                     Additional documentation
projects/                 Novel project snapshot
```

## Get started

Clone the repository and its remaining independent component:

```bash
git clone --recurse-submodules https://github.com/hunterhigh/ruwen-writing-system.git
```

The installable core plugin is located at:

```text
01-完整插件/ruwen-xiezuo-xitong/
```

The commercial advisor is maintained directly in this repository at:

```text
02-项目商业顾问/project-commercial-advisor/
```

## Design principles

- **Context isolation.** The author receives the approved creative situation, not the full planning and correction machinery.
- **Canon has an approval boundary.** Drafts and analyses do not become project truth until the user approves them.
- **Roles have narrow authority.** Readers, editors, validators, and memory maintainers contribute distinct judgments instead of collapsing into one opaque agent.
- **External knowledge remains attributable.** Research and literary references are incorporated as project resources rather than silently blended into generated prose.
- **Claims follow evidence.** Structural validation can establish package integrity; it cannot by itself prove improved literary quality.

## Versioning

The repository name is version-neutral. Product versions are managed explicitly instead of being embedded in the repository slug:

- [`VERSION`](VERSION) records the current Ruwen release line.
- [`CHANGELOG.md`](CHANGELOG.md) records user-visible changes.
- Git tags and GitHub Releases use `vMAJOR.MINOR.PATCH`.
- Installable components keep their own manifest versions when they can evolve independently.

- Current Ruwen version: **5.0.0**
- Current maturity: **Candidate**

The core package has passed its structural and automated checks. Literary quality remains a project-level outcome: a voice or domain capability is activated only after a closed audit, non-canonical trial writing, and user review.

## Background

Ruwen 5.0 was built from the frozen 2026-08-27 V4.1 `0.3.1` technical baseline as a separate plugin. The original package and the existing 《东方战国》 project were not migrated or rewritten in place.
