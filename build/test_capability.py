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
