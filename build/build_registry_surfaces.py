#!/usr/bin/env python3
"""Generate stable, machine-readable Task Library discovery surfaces.

The interactive dashboard's ``data.json`` remains the single build artifact
from which these public files are derived:

* ``task-registry.json`` — flattened task records, including the runnable
  Markdown and the current capability-index evidence.
* ``task-registry.schema.json`` — the versioned JSON contract.
* ``llms.txt`` — a compact discovery and interpretation guide.

The post-evidence step also persists each category's deterministic
``taskScoreRollup`` back into ``data.json`` so dashboard and registry clients
see the same E0 versus E1-E4 coverage.

Keeping this as a separate build step lets downstream clients rely on a small,
explicit contract without coupling the main registry resolver to an API format.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INPUT = os.path.join(ROOT, 'dashboard', 'data.json')
DEFAULT_OUTPUT_DIR = os.path.join(ROOT, 'dashboard')
SCHEMA_SOURCE = os.path.join(ROOT, 'build', 'task-registry.schema.json')
DEFAULT_BASE_URL = 'https://goodrich-dev.github.io/task-library'
CANONICAL_LIBRARY_URL = 'https://blitzmetrics.com/task-library-dashboard/'
REPOSITORY_URL = 'https://github.com/Goodrich-Dev/task-library'
SCHEMA_VERSION = '1.1'
# Two legacy, already-public task IDs contain ``--``. Preserve those stable
# identifiers while still rejecting whitespace, punctuation, and edge hyphens.
SLUG = re.compile(r'^[a-z0-9]+(?:-+[a-z0-9]+)*$')
SHA256 = re.compile(r'^[a-f0-9]{64}$')
SCORE_FIELDS = ('aiExecution', 'humanAccountability', 'automationExposure', 'readiness')
SCORE_BANDS = ('0-19', '20-39', '40-59', '60-79', '80-100')
EVIDENCE_LEVELS = ('E0', 'E1', 'E2', 'E3', 'E4')
CATEGORY_ROLLUP_GUARDRAIL = (
    'Descriptive distribution of task-level scores; not a job-replacement score '
    'or a forecast of employment outcomes.'
)


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256_text(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def humanize(slug):
    value = slug.strip()
    if ' ' in value:
        return value
    return value.replace('-', ' ').capitalize()


def require(mapping, key, context):
    if key not in mapping:
        raise ValueError(f'{context}: missing "{key}"')
    return mapping[key]


def skill_digest(task, content, slug):
    """Return the evidence digest and its provenance.

    New catalogs carry the digest of exact resolved source text, which may
    intentionally differ from the normalized Markdown embedded in data.json.
    A deterministic content hash keeps legacy catalogs readable; an empty,
    pathless tracker gap has no skill revision and therefore no digest.
    """
    if 'sourceSha256' in task:
        source_digest = task['sourceSha256']
        if source_digest is None:
            return None, 'unavailable'
        if not isinstance(source_digest, str) or not SHA256.fullmatch(source_digest):
            raise ValueError(f'{slug}: sourceSha256 must be a lowercase SHA-256 digest or null')
        return source_digest, 'resolved-source'
    if content:
        return sha256_text(content), 'legacy-catalog-content'
    return None, 'unavailable'


def validate_capability(capability, slug):
    if not isinstance(capability, dict):
        raise ValueError(f'{slug}: capability must be an object')
    for field in SCORE_FIELDS:
        value = require(capability, field, f'{slug} capability')
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            raise ValueError(f'{slug}: capability.{field} must be a number from 0 to 100')
    for field in ('version', 'evidenceLevel', 'confidence', 'mode', 'access'):
        if not isinstance(require(capability, field, f'{slug} capability'), str):
            raise ValueError(f'{slug}: capability.{field} must be a string')
    reasons = require(capability, 'reasons', f'{slug} capability')
    if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
        raise ValueError(f'{slug}: capability.reasons must be an array of strings')


def normalize_evidence(evidence, slug):
    evidence = evidence or {}
    if not isinstance(evidence, dict):
        raise ValueError(f'{slug}: evidence must be an object')
    level = evidence.get('effectiveEvidenceLevel', 'E0')
    if level not in {'E0', 'E1', 'E2', 'E3', 'E4'}:
        raise ValueError(f'{slug}: evidence.effectiveEvidenceLevel must be E0-E4')
    arm_metrics = evidence.get('armMetrics', [])
    history = evidence.get('history', [])
    if not isinstance(arm_metrics, list) or not isinstance(history, list):
        raise ValueError(f'{slug}: evidence armMetrics/history must be arrays')
    return {
        'effectiveEvidenceLevel': level,
        'effectiveRecordId': evidence.get('effectiveRecordId'),
        'resultInterpretation': evidence.get('resultInterpretation'),
        'lastTestedAt': evidence.get('lastTestedAt'),
        'expiresAt': evidence.get('expiresAt'),
        'armMetrics': arm_metrics,
        'recordCount': evidence.get('recordCount', 0),
        'activeRecordCount': evidence.get('activeRecordCount', 0),
        'history': history,
    }


def normalize_task_page(task, slug):
    task_page = task.get('taskPage') or None
    match = task.get('taskPageMatch')
    if task_page is None:
        if match is not None:
            raise ValueError(f'{slug}: taskPageMatch requires taskPage')
        return None, None
    if not isinstance(task_page, str):
        raise ValueError(f'{slug}: taskPage must be a string or null')
    parsed = urllib.parse.urlsplit(task_page)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(f'{slug}: taskPage must be an absolute HTTP(S) URL')
    if not isinstance(match, dict):
        raise ValueError(f'{slug}: mapped taskPage requires taskPageMatch metadata')
    method = require(match, 'matchMethod', f'{slug} taskPageMatch')
    canonical = match.get('canonicalTask')
    if not isinstance(method, str) or not method:
        raise ValueError(f'{slug}: taskPageMatch.matchMethod must be a non-empty string')
    if canonical is not None and (not isinstance(canonical, str) or not SLUG.fullmatch(canonical)):
        raise ValueError(f'{slug}: taskPageMatch.canonicalTask must be a task slug or null')
    return task_page, {'matchMethod': method, 'canonicalTask': canonical}


def score_band(value):
    """Return the fixed 20-point band for a validated 0-100 score."""
    return SCORE_BANDS[min(int(value) // 20, len(SCORE_BANDS) - 1)]


def median(values):
    """Return the exact middle value (or midpoint) with stable JSON numbers."""
    ordered = sorted(values)
    if not ordered:
        return 0
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    value = (ordered[midpoint - 1] + ordered[midpoint]) / 2
    return int(value) if value.is_integer() else value


def build_task_score_rollup(tasks):
    """Summarize task scorecards without manufacturing a category score.

    Evidence level describes evaluation rigor, not whether the observed result
    supports capability.  The coverage counts therefore remain neutral E0 and
    E1-E4 inventory counts; result interpretations stay on the task records.
    """
    scores = {field: [] for field in SCORE_FIELDS}
    distributions = {
        field: {band: 0 for band in SCORE_BANDS}
        for field in SCORE_FIELDS
    }
    evidence_by_level = {level: 0 for level in EVIDENCE_LEVELS}
    mode_counts = {}

    for task in tasks:
        slug = task.get('slug') or task.get('id') or 'category task'
        capability = require(task, 'capability', slug)
        validate_capability(capability, slug)
        for field in SCORE_FIELDS:
            value = capability[field]
            scores[field].append(value)
            distributions[field][score_band(value)] += 1

        mode = capability['mode']
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        evidence = task.get('evidence') or {}
        level = evidence.get('effectiveEvidenceLevel', capability.get('evidenceLevel', 'E0'))
        if level not in EVIDENCE_LEVELS:
            raise ValueError(f'{slug}: effective evidence level must be E0-E4')
        evidence_by_level[level] += 1

    task_count = len(tasks)
    e0_count = evidence_by_level['E0']
    return {
        'unitOfAnalysis': 'task',
        'taskCount': task_count,
        'medians': {field: median(scores[field]) for field in SCORE_FIELDS},
        'distributions': distributions,
        'modeCounts': dict(sorted(mode_counts.items())),
        'evidenceCoverage': {
            'e0TaskCount': e0_count,
            'e1ToE4TaskCount': task_count - e0_count,
            'byLevel': evidence_by_level,
        },
        'guardrail': CATEGORY_ROLLUP_GUARDRAIL,
    }


def attach_category_rollups(data):
    """Persist post-evidence rollups into dashboard data; return whether changed."""
    categories = require(data, 'categories', 'dashboard data')
    if not isinstance(categories, list):
        raise ValueError('dashboard data: categories must be an array')
    changed = False
    for category in categories:
        name = category.get('name') or 'category'
        tasks = require(category, 'tasks', name)
        if not isinstance(tasks, list):
            raise ValueError(f'{name}: tasks must be an array')
        expected = build_task_score_rollup(tasks)
        if category.get('taskScoreRollup') != expected:
            category['taskScoreRollup'] = expected
            changed = True
    return changed


def build_registry(data, base_url=DEFAULT_BASE_URL):
    """Return the public registry object after validating cross-file invariants."""
    if not isinstance(data, dict):
        raise ValueError('dashboard data must be a JSON object')
    stats = require(data, 'stats', 'dashboard data')
    capability_index = require(data, 'capabilityIndex', 'dashboard data')
    task_page_index = require(data, 'taskPageIndex', 'dashboard data')
    source_categories = require(data, 'categories', 'dashboard data')
    updated = require(data, 'updated', 'dashboard data')
    if not isinstance(source_categories, list):
        raise ValueError('dashboard data: categories must be an array')

    base_url = base_url.rstrip('/')
    tasks = []
    categories = []
    seen_slugs = set()
    seen_category_ids = set()

    for category in source_categories:
        category_name = require(category, 'name', 'category')
        category_id = require(category, 'folder', f'category {category_name}')
        if not SLUG.fullmatch(category_id):
            raise ValueError(f'category {category_name}: invalid folder/id "{category_id}"')
        if category_id in seen_category_ids:
            raise ValueError(f'duplicate category id: {category_id}')
        seen_category_ids.add(category_id)
        source_tasks = require(category, 'tasks', f'category {category_name}')
        if not isinstance(source_tasks, list):
            raise ValueError(f'category {category_name}: tasks must be an array')

        category_tasks = []
        for task in source_tasks:
            slug = require(task, 'slug', f'task in {category_name}')
            if not isinstance(slug, str) or not SLUG.fullmatch(slug):
                raise ValueError(f'task in {category_name}: invalid slug "{slug}"')
            if slug in seen_slugs:
                raise ValueError(f'duplicate task slug: {slug}')
            seen_slugs.add(slug)

            content = require(task, 'content', slug)
            if not isinstance(content, str):
                raise ValueError(f'{slug}: content must be a string')
            capability = require(task, 'capability', slug)
            validate_capability(capability, slug)
            article = task.get('article') or None
            task_page, task_page_match = normalize_task_page(task, slug)
            source_archive = task.get('download') or None
            if article is not None and not isinstance(article, str):
                raise ValueError(f'{slug}: article must be a string or null')
            if source_archive is not None and not isinstance(source_archive, str):
                raise ValueError(f'{slug}: download must be a string or null')
            source_digest, digest_source = skill_digest(task, content, slug)

            task_record = {
                'id': slug,
                'slug': slug,
                'name': task.get('title') or slug,
                'title': humanize(task.get('title') or slug),
                'description': task.get('desc') or '',
                'categoryId': category_id,
                'category': category_name,
                'stage': task.get('stage') or '—',
                'status': require(task, 'status', slug),
                'sourceType': task.get('sourceType') or 'unknown',
                'owner': task.get('owner') or None,
                'flag': task.get('flag') or None,
                'urls': {
                    'task': f'{base_url}/#task={slug}',
                    'taskPage': task_page,
                    'definitiveArticle': article,
                    'sourceArchive': source_archive,
                },
                'taskPageMatch': task_page_match,
                'skill': {
                    'mediaType': 'text/markdown',
                    'runnable': bool(content.strip()),
                    'sha256': source_digest,
                    'digestSource': digest_source,
                    'markdownSha256': sha256_text(content),
                    'markdown': content,
                },
                'capability': capability,
                'evidence': normalize_evidence(task.get('evidence'), slug),
            }
            tasks.append(task_record)
            category_tasks.append(task_record)

        categories.append({
            'id': category_id,
            'name': category_name,
            'description': category.get('description') or '',
            'taskCount': len(category_tasks),
            'taskScoreRollup': build_task_score_rollup(category_tasks),
        })

    expected_total = require(stats, 'total', 'dashboard stats')
    if expected_total != len(tasks):
        raise ValueError(f'dashboard stats.total is {expected_total}, but registry contains {len(tasks)} tasks')
    if require(stats, 'categories', 'dashboard stats') != len(categories):
        raise ValueError('dashboard stats.categories does not match the category array')
    actual_with_article = sum(bool(task['urls']['definitiveArticle']) for task in tasks)
    actual_without_article = len(tasks) - actual_with_article
    actual_articles = len({
        task['urls']['definitiveArticle']
        for task in tasks if task['urls']['definitiveArticle']
    })
    actual_with_task_page = sum(bool(task['urls']['taskPage']) for task in tasks)
    actual_without_task_page = len(tasks) - actual_with_task_page
    actual_task_pages = len({
        task['urls']['taskPage'] for task in tasks if task['urls']['taskPage']
    })
    for field, actual in {
        'tasksWithArticle': actual_with_article,
        'tasksWithoutArticle': actual_without_article,
        'definitiveArticles': actual_articles,
        'tasksWithTaskPage': actual_with_task_page,
        'tasksWithoutTaskPage': actual_without_task_page,
        'uniqueTaskPages': actual_task_pages,
    }.items():
        reported = require(stats, field, 'dashboard stats')
        if reported != actual:
            raise ValueError(
                f'dashboard stats.{field} is {reported}, but task records produce {actual}'
            )

    tasks_by_slug = {task['slug']: task for task in tasks}
    for task in tasks:
        match = task['taskPageMatch']
        canonical = match and match['canonicalTask']
        if not canonical:
            continue
        canonical_task = tasks_by_slug.get(canonical)
        if not canonical_task:
            raise ValueError(f'{task["slug"]}: canonicalTask {canonical} is not registered')
        if canonical_task['taskPageMatch'] and canonical_task['taskPageMatch']['canonicalTask']:
            raise ValueError(f'{task["slug"]}: canonicalTask {canonical} cannot be another alias')
        if canonical_task['urls']['taskPage'] != task['urls']['taskPage']:
            raise ValueError(f'{task["slug"]}: canonicalTask {canonical} must share taskPage URL')

    if not isinstance(task_page_index, dict):
        raise ValueError('dashboard taskPageIndex must be an object')
    for field in ('version', 'reviewedAt', 'sourceIndex', 'interpretation'):
        if not isinstance(require(task_page_index, field, 'dashboard taskPageIndex'), str):
            raise ValueError(f'dashboard taskPageIndex.{field} must be a string')

    registry = {
        '$schema': f'{base_url}/task-registry.schema.json',
        'schemaVersion': SCHEMA_VERSION,
        'name': 'BlitzMetrics Task Library',
        'description': (
            'A public task-level registry of runnable skills, manually reviewed exact '
            'task pages, documentation readiness, and evidence-labeled AI capability assessments.'
        ),
        'updated': updated,
        'links': {
            'canonicalLibrary': CANONICAL_LIBRARY_URL,
            'interactiveDashboard': f'{base_url}/',
            'registry': f'{base_url}/task-registry.json',
            'schema': f'{base_url}/task-registry.schema.json',
            'llms': f'{base_url}/llms.txt',
            'evidenceSummary': f'{base_url}/evidence-summary.json',
            'sourceRepository': REPOSITORY_URL,
            'methodology': capability_index.get('methodologyUrl') or None,
            'skillBundle': f'{base_url}/{data.get("bundleUrl", "TaskLibrary-Skills-all.zip")}',
        },
        'provenance': {
            'generatedFrom': f'{base_url}/data.json',
            'precedence': 'Asset Tracker sheet beats registry entry beats hub skill file.',
            'contentNote': 'Skill Markdown is embedded so clients do not need to scrape the dashboard.',
            'evidenceNote': 'Validated evidence is joined by task slug after the append-only ledger check.',
        },
        'semantics': {
            'status': {
                'complete': 'Documentation-complete; not proof of production reliability.',
                'needs-work': 'Runnable or partially documented, with known documentation gaps.',
                'gap': 'Defined task with missing or incomplete runnable guidance.',
            },
            'evidence': {
                'E0': 'Hypothesis or rules-based baseline; not yet validated by a representative run.',
                'E1': 'Successful demonstration on a known example.',
                'E2': 'Preregistered repeated-case or held-out trial; the result may be positive or negative.',
                'E3': 'Matched, blinded comparison with Human-only, AI-only, and Human+AI arms.',
                'E4': 'Sustained production validation with monitored outcomes, incidents, and recovery.',
            },
            'guardrail': (
                'AI execution and automation exposure are task-level measures, not job-loss '
                'probabilities. Human accountability remains a separate score.'
            ),
        },
        'stats': stats,
        'capabilityIndex': capability_index,
        'taskPageIndex': task_page_index,
        'categories': categories,
        'tasks': tasks,
    }
    # Cover the complete public payload except the self-referential revision
    # field. Any link, semantic, statistic, category, or task change must move it.
    registry_revision = sha256_text(canonical_json(registry))
    registry['registryRevision'] = f'sha256:{registry_revision}'
    return registry


def build_llms_text(registry):
    links = registry['links']
    stats = registry['stats']
    capability = registry['capabilityIndex']
    capability_note = (capability.get('note') or 'Evidence-labeled task-level assessment').rstrip('.')
    lines = [
        '# BlitzMetrics Task Library',
        '',
        '> Public operational task registry for the Content Factory and related BlitzMetrics systems. '
        'Each task includes its runnable Markdown, separately labeled exact-task and broader-hub links, '
        'documentation status, and an evidence-labeled AI capability scorecard.',
        '',
        f"Updated: {registry['updated']}",
        f"Registry revision: `{registry['registryRevision']}`",
        '',
        '## Primary resources',
        '',
        f"- [Task registry JSON]({links['registry']}): The complete machine-readable registry, including skill Markdown and capability evidence.",
        f"- [Task registry JSON Schema]({links['schema']}): Versioned contract for validating registry clients.",
        f"- [Validated evidence summary]({links['evidenceSummary']}): Append-only E1-E4 trial results joined to tasks by stable slug.",
        f"- [Public article health audit]({links['interactiveDashboard']}public-article-audit.json): Latest scheduled observation of task-linked HTTP, redirect, content, login, and canonical health.",
        f"- [Interactive Task Library]({links['interactiveDashboard']}): Human-facing search, filters, scorecards, and task detail views.",
        f"- [Canonical BlitzMetrics page]({links['canonicalLibrary']}): The first-party library page and project context.",
        f"- [Static task index]({links['interactiveDashboard']}library-index.html): Semantic HTML list of every task and definitive article.",
        f"- [Runnable skill bundle]({links['skillBundle']}): Downloadable Markdown skills rebuilt from the same source data.",
    ]
    if links.get('methodology'):
        lines.append(f"- [AI Capability Index methodology]({links['methodology']}): Definitions, evidence ladder, and interpretation guardrails.")
    lines.extend([
        '',
        '## How to use the registry',
        '',
        '1. Select a task record by its stable `slug` or `id`.',
        '2. Read `skill.markdown`, then check its inputs, access requirements, steps, and definition of done before acting.',
        '3. When `urls.taskPage` is present, use it as the manually reviewed exact task SOP. `taskPageMatch` records how it was matched and any legacy alias.',
        '4. Use `urls.definitiveArticle` for the broader hub or system context; it is not automatically an exact task SOP.',
        '5. Treat `status` as documentation readiness, not proof that the task succeeds in production.',
        '6. Treat an `E0` capability score as a low-confidence hypothesis. Prefer E2–E4 evidence for delegation decisions.',
        '7. Keep a human accountable for consent, credentials, spending, publication, relationships, and irreversible actions.',
        '',
        '## Current inventory',
        '',
        f"- {stats['total']} registered tasks across {stats['categories']} categories.",
        f"- {stats['complete']} documentation-complete; {stats['needsWork']} need work; {stats['gaps']} gaps.",
        f"- {stats['runnableSkills']} records currently resolve to runnable Markdown.",
        f"- {stats['tasksWithTaskPage']} tasks have manually reviewed exact task pages; "
        f"{stats['tasksWithoutTaskPage']} do not; aliases resolve to {stats['uniqueTaskPages']} unique pages.",
        f"- Capability Index version {capability['version']}; current baseline is {capability_note}.",
        '',
        '## Categories',
        '',
    ])
    for category in registry['categories']:
        rollup = category['taskScoreRollup']
        medians = rollup['medians']
        evidence = rollup['evidenceCoverage']
        lines.append(
            f"- **{category['name']}** ({category['taskCount']} tasks): "
            f"median task scores — AI execution {medians['aiExecution']}, "
            f"human accountability {medians['humanAccountability']}, "
            f"automation exposure {medians['automationExposure']}, "
            f"readiness {medians['readiness']}; evidence coverage — "
            f"E0 {evidence['e0TaskCount']}, E1-E4 {evidence['e1ToE4TaskCount']}. "
            f"{category['description']}"
        )
    lines.append(f"\nCategory medians are {CATEGORY_ROLLUP_GUARDRAIL.lower()}")
    lines.extend([
        '',
        '## Provenance and corrections',
        '',
        f"- [Source repository]({links['sourceRepository']}): Build scripts, registry inputs, and validation rules.",
        f"- Source precedence: {registry['provenance']['precedence']}",
        '- Machine clients should compare `registryRevision`, `skill.sha256` for exact source changes when available, or `skill.markdownSha256` for the embedded Markdown.',
        '- Report documentation or scoring errors through the source repository, then preserve the correction as a regression test.',
        '',
    ])
    return '\n'.join(lines)


def render_outputs(data, base_url=DEFAULT_BASE_URL):
    registry = build_registry(data, base_url)
    return {
        'task-registry.json': json.dumps(registry, ensure_ascii=False, indent=2) + '\n',
        'llms.txt': build_llms_text(registry),
    }


def write_if_changed(path, content):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as handle:
            if handle.read() == content:
                return False
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(content)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default=DEFAULT_INPUT)
    parser.add_argument('--out-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL)
    parser.add_argument('--check', action='store_true', help='Fail if generated outputs are absent or stale.')
    args = parser.parse_args()

    with open(args.input, encoding='utf-8') as handle:
        data = json.load(handle)
    rollups_changed = attach_category_rollups(data)
    outputs = render_outputs(data, args.base_url)
    with open(SCHEMA_SOURCE, encoding='utf-8') as handle:
        outputs['task-registry.schema.json'] = handle.read()

    if args.check:
        stale = []
        if rollups_changed:
            stale.append(os.path.basename(args.input) + ' category rollups')
        for filename, expected in outputs.items():
            path = os.path.join(args.out_dir, filename)
            if not os.path.exists(path) or open(path, encoding='utf-8').read() != expected:
                stale.append(filename)
        if stale:
            print('stale registry surfaces: ' + ', '.join(stale), file=sys.stderr)
            return 1
        print(f'checked {len(outputs)} registry surfaces; all current')
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    changed = []
    if rollups_changed:
        data_content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if write_if_changed(args.input, data_content):
            changed.append(os.path.basename(args.input) + ' category rollups')
    for filename, content in outputs.items():
        if write_if_changed(os.path.join(args.out_dir, filename), content):
            changed.append(filename)
    print(f"registry surfaces: tasks={data['stats']['total']}, changed={', '.join(changed) if changed else 'none'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
