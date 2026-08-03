"""Regression tests for the v0.1 capability-index guardrails."""

import json
from pathlib import Path
import re
import tempfile
import unittest
import zipfile

import build as task_build


def task(title, description='', inputs='- Public source material'):
    return {
        'title': title,
        'desc': description,
        'status': 'complete',
        'article': None,
        'content': (
            f'## Inputs\n{inputs}\n\n'
            '## Definition of done (QA checklist)\n- [ ] Output checked\n\n'
            '## Example(s)\n- Accepted example\n'
        ),
    }


class CapabilityGuardrailTests(unittest.TestCase):
    def score(self, value, category='Website QA Audit'):
        return task_build.score_capability(value, category)

    def test_physical_capture_never_exceeds_execution_cap(self):
        cap = self.score(task('Record one-minute videos'), 'Personal Branding')
        self.assertLessEqual(cap['aiExecution'], 30)

    def test_privileged_access_cannot_be_automation_candidate(self):
        cap = self.score(task(
            'Verify Google Business Profile',
            inputs='- Google Business Profile admin access',
        ))
        self.assertNotEqual(cap['mode'], 'Automation candidate')
        self.assertEqual(cap['access'], 'Privileged access named')

    def test_contextual_publish_mention_is_not_privileged_access(self):
        cap = self.score(task(
            'Write title and headings',
            inputs='- RankMath previews these at publish time',
        ), 'SEO & Content Architecture')
        self.assertEqual(cap['access'], 'No privileged access detected')

    def test_external_mutation_requires_accountable_review(self):
        cap = self.score(task(
            'Fix categories and tags in WordPress',
            inputs='- WordPress editor role',
        ), 'Content Factory — Post')
        self.assertGreaterEqual(cap['humanAccountability'], 50)
        self.assertNotEqual(cap['mode'], 'Automation candidate')

    def test_all_numeric_scores_are_bounded(self):
        cap = self.score(task('Draft an approved post'))
        for key in ('aiExecution', 'humanAccountability', 'automationExposure', 'readiness'):
            self.assertGreaterEqual(cap[key], 0)
            self.assertLessEqual(cap[key], 100)

    def test_legacy_double_hyphen_task_ids_remain_valid(self):
        self.assertIsNotNone(task_build.SLUG.fullmatch(
            'ensure-robots-meta-not-blocking-indexing--qa-audit'
        ))
        self.assertIsNone(task_build.SLUG.fullmatch('-invalid--slug-'))

    def test_blitzmetrics_article_url_uses_canonical_trailing_slash(self):
        self.assertEqual(
            task_build.article_url('/blog-posting-guidelines'),
            'https://blitzmetrics.com/blog-posting-guidelines/',
        )
        self.assertEqual(
            task_build.article_url('https://www.blitzmetrics.com/dad?ref=task#proof'),
            'https://www.blitzmetrics.com/dad/?ref=task#proof',
        )

    def test_article_url_does_not_rewrite_files_or_other_hosts(self):
        self.assertEqual(
            task_build.article_url('https://blitzmetrics.com/llms.txt'),
            'https://blitzmetrics.com/llms.txt',
        )
        self.assertEqual(
            task_build.article_url('https://example.com/article'),
            'https://example.com/article',
        )

    def test_unverified_agent_claim_reduces_readiness_and_is_visible(self):
        plain = task('Verify a bounded result')
        claimed = task('Verify a bounded result')
        claimed['content'] += (
            '\nA persistent agent uses memory across runs and runs automatically.'
        )
        plain_score = self.score(plain)
        claimed_score = self.score(claimed)
        self.assertLess(claimed_score['readiness'], plain_score['readiness'])
        self.assertIn(
            'Unverified agent persistence or memory claim in skill',
            claimed_score['reasons'],
        )

    def test_skill_bundle_includes_shared_operating_contract(self):
        data = {
            'categories': [{
                'name': 'Website QA Audit',
                'tasks': [{
                    'slug': 'verify-one-thing',
                    'status': 'complete',
                    'content': '# Verify one thing\n',
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            count = task_build.write_zip(data, directory, 'skills.zip', 'test', False)
            with zipfile.ZipFile(Path(directory) / 'skills.zip') as archive:
                names = set(archive.namelist())
                manifest = json.loads(
                    archive.read('TaskLibrary-Skills/manifest.json').decode('utf-8')
                )
        self.assertEqual(count, 1)
        self.assertIn('TaskLibrary-Skills/boil-the-ocean.md', names)
        self.assertEqual(manifest['total'], 1)
        self.assertEqual(manifest['operatingContract'], 'boil-the-ocean.md')

    def test_tracker_only_and_override_rows_share_canonical_article_policy(self):
        self.assertEqual(
            task_build.tracker_article_url({
                'Definitive Article URL': ' /what-is-a-knowledge-panel '
            }),
            'https://blitzmetrics.com/what-is-a-knowledge-panel/',
        )
        self.assertIsNone(task_build.tracker_article_url({
            'Definitive Article URL': ''
        }))

    def test_reviewed_task_page_map_attaches_no_inferred_pages_and_deduplicates_alias(self):
        index = task_build.load_task_page_index()
        tasks = [{'slug': slug} for slug in index['tasks']]
        tasks.append({'slug': 'unmapped-task'})
        stats = task_build.attach_task_pages(tasks, index)
        by_slug = {item['slug']: item for item in tasks}
        self.assertEqual(stats, {
            'tasksWithTaskPage': len(index['tasks']),
            'tasksWithoutTaskPage': 1,
            'uniqueTaskPages': len({match['url'] for match in index['tasks'].values()}),
        })
        self.assertIsNone(by_slug['unmapped-task']['taskPage'])
        self.assertIsNone(by_slug['unmapped-task']['taskPageMatch'])
        alias = by_slug['how-to-process-videos-via-marketscale']
        canonical = by_slug['process-videos-via-marketscale']
        self.assertEqual(alias['taskPageMatch'], {
            'matchMethod': 'legacy-alias',
            'canonicalTask': 'process-videos-via-marketscale',
        })
        self.assertEqual(alias['taskPage'], canonical['taskPage'])

    def test_task_page_map_rejects_alias_url_drift(self):
        index = task_build.load_task_page_index()
        index['tasks']['how-to-process-videos-via-marketscale']['url'] = (
            'https://blitzmetrics.com/not-the-canonical-task-page/'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'task-pages.json'
            path.write_text(json.dumps(index), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'alias URL'):
                task_build.load_task_page_index(path)

    def test_static_index_labels_exact_task_page_separately_from_broader_hub(self):
        data = {
            'updated': 'August 2, 2026',
            'stats': {
                'total': 1, 'categories': 1, 'tasksWithTaskPage': 1,
                'tasksWithoutTaskPage': 0, 'complete': 1, 'needsWork': 0, 'gaps': 0,
            },
            'categories': [{
                'name': 'Website QA Audit',
                'description': 'Checks',
                'tasks': [{
                    'slug': 'verify-one-thing', 'title': 'verify-one-thing',
                    'desc': 'Verify one bounded thing',
                    'taskPage': 'https://blitzmetrics.com/exact-task/',
                    'article': 'https://blitzmetrics.com/broader-hub/',
                    'capability': {
                        'aiExecution': 80, 'humanAccountability': 40,
                        'automationExposure': 58,
                    },
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library-index.html'
            task_build.write_library_index(data, path)
            output = path.read_text(encoding='utf-8')
        self.assertIn('>Exact task SOP</a>', output)
        self.assertIn('>Broader definitive hub</a>', output)
        self.assertNotIn('>Definitive article</a>', output)

    def test_skill_links_use_the_current_knowledge_panel_canonical(self):
        skills = Path(__file__).resolve().parents[1] / 'skills'
        legacy = re.compile(r'(?<![a-z-])/knowledge-panel(?=$|[\s).,/?#])')
        offenders = []
        current_links = 0
        for path in skills.rglob('*.md'):
            text = path.read_text(encoding='utf-8')
            if legacy.search(text):
                offenders.append(str(path.relative_to(skills)))
            current_links += text.count('/what-is-a-knowledge-panel')
        self.assertEqual(offenders, [])
        self.assertGreater(current_links, 0)


if __name__ == '__main__':
    unittest.main()
