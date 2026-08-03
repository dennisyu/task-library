"""Regression tests for the v0.1 capability-index guardrails."""

import unittest

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


if __name__ == '__main__':
    unittest.main()
