#!/usr/bin/env python3
"""Task Library build: resolve registry -> validate skills -> compose dashboard data.json.

Sources per skill (build/registry.json):
  "local"                                   -> skills/<category-folder>/<slug>.md
  "github:<owner>/<repo>@<ref>:<path>"      -> fetched from raw.githubusercontent.com

External fetches are cached in build/.cache/; on fetch failure the last good
copy is used (with a warning) so a deleted or renamed repo never blanks a skill.

Optional: --tracker-csv <file> overrides status/owner/article per slug from the
Asset Tracker's published CSV (columns: Slug, Status, Owner, Definitive Article URL).

Usage:
  python3 build/build.py [--tracker-csv tracker.csv] [--out dashboard/data.json]
Exit code 1 if any skill fails validation (build still writes valid skills).
"""
import argparse, csv, hashlib, json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build')
CACHE = os.path.join(BUILD, '.cache')

STAGES = {'Produce', 'Process', 'Post', 'Promote', '—', ''}
STATUSES = {'complete', 'needs-work', 'gap'}
# Preserve two already-public legacy task IDs that contain a double hyphen.
# New IDs should still use ordinary lowercase kebab-case.
SLUG = re.compile(r'^[a-z0-9]+(?:-+[a-z0-9]+)*$')
REQUIRED_FM = ['name', 'description', 'category', 'stage', 'definitive_article', 'status']
REQUIRED_SECTIONS = ['## Inputs', '## Steps', '## Definition of done (QA checklist)',
                     '## Example(s)', '## Definitive article & links']
STUB = re.compile(r'(placeholder|TBD|to be (written|documented|filled)|coming soon|lorem ipsum)', re.I)

CAPABILITY_VERSION = '0.1'
CAPABILITY_BASE = {
    'Content Factory — Produce': 35,
    'Content Factory — Process': 88,
    'Content Factory — Post': 78,
    'Content Factory — Promote': 68,
    'Digital Plumbing': 70,
    'Dollar a Day Campaigns': 72,
    'Website QA Audit': 90,
    'SEO & Content Architecture': 84,
    'Personal Branding': 64,
    'Strategy & Measurement': 74,
    'Thank You Machine': 54,
    'Knowledge System Maintenance': 82,
    'Gaps & Tasks to Create': 62,
}

PHYSICAL = re.compile(
    r'\b(record|film|filming|camera|conference presentation|casual conversation|take photos?|headshots?|'
    r'capture client|capture stories|phone video|in[- ]person)\b', re.I)
RELATIONSHIP = re.compile(
    r'\b(outreach|engage with (?:social )?comments|collaborat(?:e|ive)|industry peers?|get featured|'
    r'podcast guest|thank[- ]you|testimonial|referral|partnership|pitch|interview|unhappy client|negotiate)\b', re.I)
DETERMINISTIC = re.compile(
    r'\b(check|verify|audit|validate|compare|measure|extract|transcribe|proofread|configure|install|test|'
    r'ensure|categorize|tag|identify|calculate|inventory|reconcile|detect|scan)\b', re.I)
GENERATIVE = re.compile(
    r'\b(write|create|draft|repurpose|outline|summarize|edit|clip|format|generate|schema markup|'
    r'meta descriptions?|title tags?)\b', re.I)
JUDGMENT = re.compile(
    r'\b(strategy|recommend|prioritize|diagnose|decide|select|strongest|best|brand voice|audience|offer|'
    r'performance|unsupported claims?|editorial|business outcome)\b', re.I)
EXTERNAL_ACTION = re.compile(
    r'\b(publish|post to|send|email|dm|upload|boost|launch|submit|approve|invite|grant|campaign|budget|'
    r'kill|scale|claim|change|update|delete|remove|fix|set|configure dns|registrar|business manager|'
    r'wordpress author)\b', re.I)
SPEND = re.compile(r'\b(ads?|ad set|budget|campaign|spend|boost|dollar[- ]a[- ]day|scale winners?|kill underperformers?)\b', re.I)
HIGH_STAKES = re.compile(
    r'\b(legal|medical|privacy|permission|consent|financial|invoice|contract|copyright|domain ownership|'
    r'dns|dmarc|reputation)\b', re.I)
LONG_HORIZON = re.compile(r'\b(schedule|weekly|monthly|quarterly|monitor|maintain|recruit|multiweek|ongoing)\b', re.I)
ACCESS_NEEDED = re.compile(
    r'\b(log ?in|admin|credential|password|permission|account access|business manager|wordpress|'
    r'google business profile|registrar|dns|payment|budget|publish|send|upload|post to|campaign)\b', re.I)
ACCESS_INPUT = re.compile(
    r'\b(log ?in|login|admin(?:istrator)?|editor role|credential|password|permission|account access|'
    r'access to (?:the )?(?:account|site|dashboard|profile)|business manager access|registrar access|'
    r'dns access|wordpress access)\b', re.I)
ACCESS_GUIDANCE = re.compile(
    r'\b(access|login|log in|admin|permission|role|credential|account|business manager|website url|'
    r'drive folder|tracker)\b', re.I)


def clamp(n, low=0, high=100):
    return max(low, min(high, int(round(n))))


def section(text, heading):
    m = re.search(r'^##\s+' + heading + r'\s*$\n(.*?)(?=^##\s+|\Z)', text or '', re.I | re.M | re.S)
    return m.group(1).strip() if m else ''


def score_capability(task, category):
    """Transparent v0.1 task score, not a claim about whole-job replacement.

    AI execution estimates the share a current tool-using agent can perform.
    Human accountability measures how strongly a person must own consent,
    relationships, spend, judgment, or physical-world action. Automation
    exposure is deliberately lower when accountability stays human.
    """
    title_desc = ((task.get('title') or '').replace('-', ' ') + ' ' + (task.get('desc') or '')).strip()
    content = task.get('content') or ''
    all_text = title_desc + '\n' + content
    inputs = section(content, r'Inputs')
    examples = section(content, r'Example(?:\(s\))?')

    flags = {
        'physical': bool(PHYSICAL.search(title_desc)),
        'relationship': bool(RELATIONSHIP.search(title_desc)),
        'deterministic': bool(DETERMINISTIC.search(title_desc)),
        'generative': bool(GENERATIVE.search(title_desc)),
        'judgment': bool(JUDGMENT.search(title_desc)),
        'externalAction': bool(EXTERNAL_ACTION.search(title_desc)),
        'spend': bool(SPEND.search(title_desc)),
        'highStakes': bool(HIGH_STAKES.search(all_text)),
        'longHorizon': bool(LONG_HORIZON.search(title_desc)),
    }

    execution = CAPABILITY_BASE.get(category, 65)
    reasons = []
    if flags['deterministic']:
        execution += 8
        reasons.append('Checkable, structured work')
    if flags['generative']:
        execution += 7
        reasons.append('Digital creation or transformation')
    if flags['judgment']:
        execution -= 8
        reasons.append('Requires contextual judgment')
    if flags['externalAction']:
        execution -= 5
        reasons.append('Changes an external system')
    if flags['relationship']:
        execution -= 24
        reasons.append('Trust or relationship work stays human')
    if flags['longHorizon']:
        execution -= 5
        reasons.append('Persistent follow-through required')
    if flags['physical']:
        reasons.insert(0, 'Physical-world capture required')
    if re.search(r'^##\s+Definition of done', content, re.I | re.M):
        execution += 4
    if not content.strip():
        execution -= 12
        reasons.append('No runnable skill content yet')
    if flags['physical']:
        execution = min(execution, 30)
    execution = clamp(execution, 8, 98)

    access_required = bool(ACCESS_NEEDED.search(title_desc) or ACCESS_INPUT.search(inputs))
    access_documented = bool(ACCESS_GUIDANCE.search(inputs)) if access_required else True

    accountability = 24
    if category in ('Content Factory — Post', 'Content Factory — Promote', 'Dollar a Day Campaigns'):
        accountability += 10
    if category in ('Personal Branding', 'Strategy & Measurement', 'Thank You Machine'):
        accountability += 12
    if flags['deterministic']:
        accountability -= 8
    if flags['generative']:
        accountability += 4
    if flags['judgment']:
        accountability += 18
    if flags['externalAction']:
        accountability += 22
    if flags['spend']:
        accountability += 22
    if flags['highStakes']:
        accountability += 18
    if flags['relationship']:
        accountability += 32
    if access_required:
        accountability += 14
        reasons.append('Privileged access requires accountable review')
    if flags['physical']:
        accountability = max(accountability, 86)
    accountability = clamp(accountability, 8, 96)

    readiness = {'complete': 78, 'needs-work': 54, 'gap': 24}.get(task.get('status'), 40)
    if task.get('article'):
        readiness += 10
    if inputs:
        readiness += 5
    if re.search(r'^##\s+Definition of done', content, re.I | re.M):
        readiness += 5
    real_example = any(
        line.lstrip().startswith('-') and not STUB.search(line) and not re.search(r'example needed|candidate', line, re.I)
        for line in examples.splitlines())
    readiness += 8 if real_example else -5

    if access_required and not access_documented:
        readiness -= 10
    readiness = clamp(readiness, 10, 100)

    automation_exposure = clamp(execution * (1 - 0.70 * accountability / 100), 3, 95)
    if execution >= 80 and accountability < 35 and not access_required:
        mode = 'Automation candidate'
    elif execution >= 65 and accountability < 70:
        mode = 'Agent + reviewer'
    elif execution >= 35:
        mode = 'Human-led + AI'
    else:
        mode = 'Human-owned'
    access = ('Privileged access named' if access_required and access_documented else
              'Access guidance missing' if access_required else 'No privileged access detected')

    return {
        'version': CAPABILITY_VERSION,
        'aiExecution': execution,
        'humanAccountability': accountability,
        'automationExposure': automation_exposure,
        'readiness': readiness,
        'evidenceLevel': 'E0',
        'confidence': 'low',
        'mode': mode,
        'access': access,
        'reasons': reasons[:3] or ['Bounded task with a documented QA gate'],
    }


def folder_of(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower().replace('—', ' ')).strip('-')


def parse_frontmatter(text):
    m = re.match(r'---\s*\n(.*?)\n---\s*\n', text, re.S)
    if not m:
        return None, text
    fm, key = {}, None
    for line in m.group(1).splitlines():
        if line[:1] in (' ', '\t') and key:          # continuation of folded/multiline value
            fm[key] = (fm[key] + ' ' + line.strip()).strip()
            continue
        if ':' in line:
            k, v = line.split(':', 1)
            v = v.strip()
            if v in ('>', '>-', '|', '|-'):
                v = ''                                # folded block scalar starts
            elif len(v) > 1 and v[0] == v[-1] and v[0] in '"\'':
                v = v[1:-1]
            key = k.strip()
            fm[key] = v
    return fm, text[m.end():]


def resolve(slug, entry, errors, warnings):
    src = entry['source']
    if src == 'local':
        path = os.path.join(ROOT, 'skills', folder_of(entry['category']), slug + '.md')
        if not os.path.exists(path):
            errors.append(f'{slug}: local file missing ({os.path.relpath(path, ROOT)})')
            return None
        return open(path, encoding='utf-8').read()

    m = re.match(r'github:([^/]+)/([^@]+)@([^:]+):(.+)', src)
    if not m:
        errors.append(f'{slug}: unrecognized source "{src}"')
        return None
    owner, repo, ref, path = m.groups()
    url = f'https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}'
    cache_file = os.path.join(CACHE, slug + '.md')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'task-library-build'})
        tok = os.environ.get('SKILLS_READ_TOKEN')
        if tok:
            req.add_header('Authorization', 'Bearer ' + tok)
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode('utf-8')
        os.makedirs(CACHE, exist_ok=True)
        open(cache_file, 'w', encoding='utf-8').write(text)
        return text
    except Exception as e:
        if os.path.exists(cache_file):
            warnings.append(f'{slug}: fetch failed ({e}); using cached copy')
            return open(cache_file, encoding='utf-8').read()
        errors.append(f'{slug}: fetch failed ({e}) and no cached copy')
        return None


def validate(slug, entry, text, errors, warnings):
    fm, body = parse_frontmatter(text)
    if fm is None:
        errors.append(f'{slug}: missing frontmatter block')
        return None
    if entry.get('format') == 'claude-skill':
        # Standard Claude skill: frontmatter has name+description only.
        # Library metadata (category/stage/status/article) comes from the
        # registry entry (overridable by the tracker CSV), not the file.
        for k in ('name', 'description'):
            if not fm.get(k):
                errors.append(f'{slug}: claude-skill missing frontmatter "{k}"')
                return None
        if fm['name'] != slug:
            warnings.append(f'{slug}: claude-skill name "{fm["name"]}" differs from registry slug (registry wins)')
        stage = entry.get('stage', '—')
        status = entry.get('status', 'needs-work')
        if stage not in STAGES or status not in STATUSES:
            errors.append(f'{slug}: registry has invalid stage/status for claude-skill')
            return None
        desc = re.split(r'(?<=[.!?]) ', fm['description'])[0][:300]
        return {'name': slug, 'description': desc, 'category': entry['category'],
                'stage': stage, 'status': status,
                'definitive_article': entry.get('article', '')}
    for k in REQUIRED_FM:
        if k not in fm or not fm[k]:
            errors.append(f'{slug}: frontmatter missing "{k}"')
            return None
    if fm['name'] != slug:
        errors.append(f'{slug}: frontmatter name "{fm["name"]}" must equal registry slug')
        return None
    if fm['category'] != entry['category']:
        warnings.append(f'{slug}: frontmatter category "{fm["category"]}" != registry "{entry["category"]}" (registry wins)')
    if fm['stage'] not in STAGES:
        errors.append(f'{slug}: invalid stage "{fm["stage"]}"')
        return None
    if fm['status'] not in STATUSES:
        errors.append(f'{slug}: invalid status "{fm["status"]}"')
        return None
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    if missing:
        errors.append(f'{slug}: missing sections {missing}')
        return None
    if len(re.findall(r'^\d+\.', body, re.M)) < 3:
        warnings.append(f'{slug}: fewer than 3 numbered steps')
    if fm['status'] == 'complete' and STUB.search(text):
        warnings.append(f'{slug}: status complete but contains stub language')
    return fm


def article_url(v):
    if not v or v.lower().startswith('gap'):
        return None
    if v.startswith('http'):
        return v
    if v.startswith('/'):
        return 'https://blitzmetrics.com' + v
    return None


def html_escape(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def write_library_index(data, out_path):
    """Crawlable HTML fragment for the WordPress page (paste below the iframe).

    Plain semantic markup, no scripts/styles: categories as H2s, each task
    linking to its definitive article on blitzmetrics.com. This is the
    indexable representation of the library; the iframe stays the interactive one.
    """
    L = []
    st = data['stats']
    L.append('<!-- Task Library static index — generated by build.py; do not edit by hand -->')
    L.append('<section id="task-library-index">')
    L.append(f"<p>The BlitzMetrics Task Library registers <strong>{st['total']} operational tasks</strong> "
             f"across {st['categories']} categories. Each record opens the current skill and links a definitive "
             f"article where one exists; missing context, access, examples, or hubs stay visible as gaps. "
             f"{st['complete']} are marked complete, {st['needsWork']} need work, and {st['gaps']} are gaps. "
             f"Status describes documentation readiness, not proven production reliability. "
             f"Updated {html_escape(data['updated'])}.</p>")
    for c in data['categories']:
        L.append(f"<h2>{html_escape(c['name'])}</h2>")
        L.append(f"<p>{html_escape(c['description'])}</p>")
        L.append('<ul>')
        for t in c['tasks']:
            label = html_escape(t['title'].replace('-', ' ').capitalize())
            desc = html_escape((t['desc'] or '').rstrip().rstrip('.'))
            task_url = 'https://goodrich-dev.github.io/task-library/#task=' + html_escape(t['slug'])
            cap = t.get('capability') or {}
            score = (f' AI execution {cap.get("aiExecution", "—")}/100; '
                     f'human accountability {cap.get("humanAccountability", "—")}/100; '
                     f'automation exposure {cap.get("automationExposure", "—")}/100.')
            article = (f' <a href="{html_escape(t["article"])}">Definitive article</a>.'
                       if t.get('article') else '')
            L.append(f'<li><a href="{task_url}">{label}</a> — {desc}.{html_escape(score)}{article}</li>')
        L.append('</ul>')
    L.append('</section>')
    open(out_path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')


def source_from_repo_url(url, slug):
    """Turn a pasted GitHub URL into a github:owner/repo@ref:path source.

    Accepts:
      github:owner/repo@ref:path            (already a source ref — used as-is)
      https://github.com/owner/repo         -> @main:skills/<slug>/SKILL.md
      https://github.com/owner/repo/tree/<ref>/<folder>  -> <folder>/SKILL.md
      https://github.com/owner/repo/blob/<ref>/<file.md> -> that file
    """
    url = url.strip().rstrip('/')
    if url.startswith('github:'):
        return url
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)(?:/(tree|blob)/([^/]+)/(.+))?$', url)
    if not m:
        return None
    owner, repo, kind, ref, path = m.groups()
    if not kind:
        return f'github:{owner}/{repo}@main:skills/{slug}/SKILL.md'
    if kind == 'blob':
        return f'github:{owner}/{repo}@{ref}:{path}'
    return f'github:{owner}/{repo}@{ref}:{path}/SKILL.md'


def download_from_source(source):
    m = re.match(r'github:([^/]+)/([^@]+)@([^:]+):', source or '')
    if not m:
        return None
    owner, repo, ref = m.groups()
    return f'https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip' if not re.fullmatch(r'[0-9a-f]{7,40}', ref) \
        else f'https://github.com/{owner}/{repo}/archive/{ref}.zip'


def write_zip(data, out_dir, fname, note, only_complete):
    import zipfile
    ready = [(c, t) for c in data['categories'] for t in c['tasks']
             if (t.get('content') or '').strip() and (t['status'] == 'complete' or not only_complete)]
    path = os.path.join(out_dir, fname)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        manifest = {'total': len(ready), 'note': note, 'tasks': []}
        for c, t in ready:
            cf = folder_of(c['name'])
            z.writestr(f'TaskLibrary-Skills/skills/{cf}/{t["slug"]}.md', t['content'])
            manifest['tasks'].append({'slug': t['slug'], 'category': c['name'], 'status': t['status'],
                                      'owner': t.get('owner', ''), 'path': f'skills/{cf}/{t["slug"]}.md'})
        z.writestr('TaskLibrary-Skills/manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
    return len(ready)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tracker-csv')
    ap.add_argument('--out', default=os.path.join(ROOT, 'dashboard', 'data.json'))
    args = ap.parse_args()

    registry = json.load(open(os.path.join(BUILD, 'registry.json'), encoding='utf-8'))['skills']
    cats_meta = json.load(open(os.path.join(BUILD, 'categories.json'), encoding='utf-8'))
    site = json.load(open(os.path.join(BUILD, 'site-meta.json'), encoding='utf-8'))

    overrides = {}
    if args.tracker_csv:
        for row in csv.DictReader(open(args.tracker_csv, encoding='utf-8-sig')):
            overrides[row['Slug'].strip()] = row

    # Sheet-first onboarding: a tracker row with a Source Repo link whose slug
    # is not in the registry becomes a new external skill (format claude-skill).
    valid_cats = {c['name'] for c in cats_meta}
    errors, warnings = [], []
    sheet_only = {}   # rows with no source anywhere: rendered as named gap cards
    for slug, row in list(overrides.items()):
        if not SLUG.fullmatch(slug or ''):
            errors.append(f'{slug or "(blank)"}: tracker Slug must be lowercase kebab-case')
            continue
        src_cell = (row.get('Source Repo') or '').strip()
        if slug in registry and src_cell:
            # SHEET WINS: a repo link on an existing row re-points the skill
            # to the owner's repo; the hub copy is ignored from now on.
            src = source_from_repo_url(src_cell, slug)
            if src and src != registry[slug].get('source'):
                registry[slug] = dict(registry[slug], source=src, format='claude-skill',
                                      flag='claimed via sheet — hub copy superseded')
                dl = (row.get('Download URL') or '').strip() or download_from_source(src)
                if dl:
                    registry[slug]['download'] = dl
            continue
        if slug in registry:
            continue
        stage_cell = (row.get('Stage') or '—').strip() or '—'
        if stage_cell not in STAGES:
            errors.append(f'{slug}: tracker Stage "{stage_cell}" is invalid')
            continue
        if not src_cell:
            cat = (row.get('Category') or '').strip()
            if cat in valid_cats and slug:
                sheet_only[slug] = {
                    'title': (row.get('Task Title') or slug).strip() or slug,
                    'slug': slug, 'status': 'gap',
                    'stage': stage_cell,
                    'article': (row.get('Definitive Article URL') or '').strip() or None,
                    'desc': (row.get('Description') or '').strip(),
                    'content': '',
                    'flag': 'defined in sheet — not yet built',
                    'category': cat}
                if (row.get('Owner') or '').strip():
                    sheet_only[slug]['owner'] = row['Owner'].strip()
            continue
        src = source_from_repo_url(row['Source Repo'], slug)
        if not src:
            errors.append(f'{slug}: sheet Source Repo not a recognizable GitHub URL: {row["Source Repo"]}')
            continue
        cat = (row.get('Category') or '').strip()
        if cat not in valid_cats:
            errors.append(f'{slug}: sheet Category "{cat}" is not one of the {len(valid_cats)} library categories')
            continue
        tracker_status = (row.get('Status') or '').strip().lower()
        status_map = {'ready': 'complete', 'complete': 'complete', 'wip': 'needs-work',
                      'needs-work': 'needs-work', 'gap': 'gap'}
        if tracker_status and tracker_status not in status_map:
            errors.append(f'{slug}: tracker Status "{tracker_status}" is invalid')
            continue
        entry = {'source': src, 'format': 'claude-skill', 'category': cat,
                 'stage': stage_cell,
                 'status': status_map.get(tracker_status, 'needs-work'),
                 'flag': 'added via Asset Tracker sheet'}
        dl = (row.get('Download URL') or '').strip() or download_from_source(src)
        if dl:
            entry['download'] = dl
        registry[slug] = entry
    by_cat = {c['name'] for c in cats_meta} and {c['name']: [] for c in cats_meta}
    for slug, entry in registry.items():
        text = resolve(slug, entry, errors, warnings)
        if text is None:
            continue
        # Evidence records bind the exact resolved source text. Keep this
        # digest separate from the presentation-normalized ``content`` field:
        # stripping a terminal newline must not make valid evidence look stale.
        source_sha256 = hashlib.sha256(text.encode('utf-8')).hexdigest()
        fm = validate(slug, entry, text, errors, warnings)
        if fm is None:
            continue
        status, art = fm['status'], article_url(fm['definitive_article'])
        ov = overrides.get(slug)
        if ov:
            s = (ov.get('Status') or '').strip().lower()
            status = {'ready': 'complete', 'complete': 'complete', 'wip': 'needs-work', 'needs-work': 'needs-work', 'gap': 'gap'}.get(s, status)
            if (ov.get('Definitive Article URL') or '').strip():
                art = ov['Definitive Article URL'].strip()   # sheet overrides only when filled; file frontmatter is the default
        task = {'title': fm['name'], 'slug': slug, 'status': status,
                'stage': fm['stage'] or '—', 'article': art,
                'desc': fm['description'], 'content': text.strip(),
                'sourceSha256': source_sha256,
                'sourceType': 'hub' if entry.get('source') == 'local' else 'spoke'}
        task['capability'] = score_capability(task, entry['category'])
        if entry.get('flag'):
            task['flag'] = entry['flag']
        if entry.get('download'):
            task['download'] = entry['download']
        if ov and (ov.get('Owner') or '').strip():
            task['owner'] = ov['Owner'].strip()
        if entry['category'] not in by_cat:
            errors.append(f'{slug}: unknown category "{entry["category"]}"')
            continue
        by_cat[entry['category']].append(task)

    # governance: ready/wip means someone owns it; unclaimed skills are gaps
    for slug, row in overrides.items():
        st_ = (row.get('Status') or '').strip().lower()
        if st_ in ('ready', 'wip') and not (row.get('Owner') or '').strip():
            warnings.append(f'{slug}: sheet says "{st_}" but Owner is blank — unclaimed skills should be "gap"')
    # one file, one skill: flag rows resolving to the same source file
    seen_src = {}
    for slug, entry in registry.items():
        src = entry.get('source')
        if src and src != 'local':
            if src in seen_src:
                warnings.append(f'{slug}: same source file as "{seen_src[src]}" ({src}) — two rows, one file')
            seen_src[src] = slug
    for slug, t in sheet_only.items():
        cat = t.pop('category')
        t['sourceType'] = 'tracker-gap'
        # A tracker-only gap has no resolved skill source to hash. Keeping the
        # absence explicit prevents the empty presentation string from being
        # misrepresented as a tested skill revision.
        t['sourceSha256'] = None
        t['capability'] = score_capability(t, cat)
        by_cat[cat].append(t)
    all_tasks = [t for ts in by_cat.values() for t in ts]
    ai_scores = sorted(t['capability']['aiExecution'] for t in all_tasks)
    exposure_scores = sorted(t['capability']['automationExposure'] for t in all_tasks)
    mid = len(ai_scores) // 2
    median_ai = (ai_scores[mid] if len(ai_scores) % 2 else round((ai_scores[mid - 1] + ai_scores[mid]) / 2)) if ai_scores else 0
    median_exposure = (exposure_scores[mid] if len(exposure_scores) % 2 else round((exposure_scores[mid - 1] + exposure_scores[mid]) / 2)) if exposure_scores else 0
    mode_counts = {}
    for t in all_tasks:
        mode = t['capability']['mode']
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
    data = {'stats': {'total': len(all_tasks),
                      'complete': sum(t['status'] == 'complete' for t in all_tasks),
                      'needsWork': sum(t['status'] == 'needs-work' for t in all_tasks),
                      'gaps': sum(t['status'] == 'gap' for t in all_tasks),
                      'runnableSkills': sum(bool((t.get('content') or '').strip()) for t in all_tasks),
                      'readySkills': sum(t['status'] == 'complete' and bool((t.get('content') or '').strip()) for t in all_tasks),
                      'hubSkills': sum(t.get('sourceType') == 'hub' for t in all_tasks),
                      'spokeSkills': sum(t.get('sourceType') == 'spoke' for t in all_tasks),
                      'trackerGaps': sum(t.get('sourceType') == 'tracker-gap' for t in all_tasks),
                      'definitiveArticles': len({t['article'] for t in all_tasks if t.get('article')}),
                      'owners': len({t['owner'] for t in all_tasks if t.get('owner')}),
                      'categories': len(cats_meta)},
            'capabilityIndex': {
                'version': CAPABILITY_VERSION,
                'asOf': site.get('capabilityAsOf', site['updated']),
                'methodologyUrl': site.get('capabilityMethodologyUrl', ''),
                'medianAIExecution': median_ai,
                'medianAutomationExposure': median_exposure,
                'highExecutionTasks': sum(s >= 80 for s in ai_scores),
                'highAutomationTasks': sum(s >= 65 for s in exposure_scores),
                'modeCounts': mode_counts,
                'note': 'Task-level E0 baseline; automation exposure is not a forecast of whole-job loss.'
            },
            'bundleUrl': 'TaskLibrary-Skills-all.zip', 'metaArticleUrl': site['metaArticleUrl'],
            'updated': site['updated'],
            'categories': [dict(c, tasks=by_cat[c['name']]) for c in cats_meta]}

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(data, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    write_library_index(data, os.path.join(os.path.dirname(args.out), 'library-index.html'))
    nall = write_zip(data, os.path.dirname(args.out), 'TaskLibrary-Skills-all.zip',
                     'All registered task records that resolve to runnable skill content. Rebuilt on every library build.', False)
    nready = write_zip(data, os.path.dirname(args.out), 'TaskLibrary-Skills-ready.zip',
                       'Runnable skills marked documentation-complete. Ownership is not implied. Rebuilt on every library build.', True)
    print(f'zips: all={nall}, ready={nready}')

    print(f"built {len(all_tasks)}/{len(registry) + len(sheet_only)} skills -> {os.path.relpath(args.out, ROOT)}")
    print(f"stats: {data['stats']}")
    for w in warnings:
        print('WARN ', w)
    for e in errors:
        print('ERROR', e)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
