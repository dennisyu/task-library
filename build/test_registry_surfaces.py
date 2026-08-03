"""Regression tests for the public Task Library registry surfaces."""

import copy
import json
import unittest
from pathlib import Path

import build_registry_surfaces as surfaces
import validate_evidence as schema_validator


def capability():
    return {
        'version': '0.1',
        'aiExecution': 80,
        'humanAccountability': 40,
        'automationExposure': 58,
        'readiness': 70,
        'evidenceLevel': 'E0',
        'confidence': 'low',
        'mode': 'Agent + reviewer',
        'access': 'No privileged access detected',
        'reasons': ['Bounded task with a documented QA gate'],
    }


def fixture_data():
    task = {
        'title': 'test-a-public-page',
        'slug': 'test-a-public-page',
        'status': 'complete',
        'stage': 'Process',
        'article': 'https://blitzmetrics.com/example/',
        'desc': 'Test one public page against an acceptance checklist.',
        'content': '# Test a public page\n\n## Inputs\n- URL',
        # Simulate build.py preserving a terminal newline in the exact-source
        # digest while normalizing it out of dashboard presentation content.
        'sourceSha256': surfaces.sha256_text('# Test a public page\n\n## Inputs\n- URL\n'),
        'sourceType': 'hub',
        'flag': 'review after first production run',
        'taskPage': 'https://blitzmetrics.com/test-a-public-page/',
        'taskPageMatch': {
            'matchMethod': 'manual-content-review',
            'canonicalTask': None,
        },
        'capability': capability(),
    }
    return {
        'stats': {
            'total': 1,
            'complete': 1,
            'needsWork': 0,
            'gaps': 0,
            'runnableSkills': 1,
            'readySkills': 1,
            'hubSkills': 1,
            'spokeSkills': 0,
            'trackerGaps': 0,
            'definitiveArticles': 1,
            'tasksWithArticle': 1,
            'tasksWithoutArticle': 0,
            'tasksWithTaskPage': 1,
            'tasksWithoutTaskPage': 0,
            'uniqueTaskPages': 1,
            'owners': 0,
            'categories': 1,
        },
        'capabilityIndex': {
            'version': '0.1',
            'asOf': 'August 2, 2026',
            'methodologyUrl': 'https://blitzmetrics.com/content-factory-ai-capability-index/',
            'medianAIExecution': 80,
            'medianAutomationExposure': 58,
            'highExecutionTasks': 1,
            'highAutomationTasks': 0,
            'modeCounts': {'Agent + reviewer': 1},
            'note': 'Task-level E0 baseline; not a forecast of whole-job loss.',
        },
        'bundleUrl': 'TaskLibrary-Skills-all.zip',
        'taskPageIndex': {
            'version': '1.0',
            'reviewedAt': '2026-08-02',
            'sourceIndex': 'https://blitzmetrics.com/the-task-library/',
            'interpretation': 'Exact task SOP pages are manually reviewed separately from broader hubs.',
        },
        'updated': 'August 2, 2026',
        'categories': [{
            'folder': 'website-qa-audit',
            'name': 'Website QA Audit',
            'description': 'Check the public website against explicit acceptance criteria.',
            'tasks': [task],
        }],
    }


class RegistrySurfaceTests(unittest.TestCase):
    def test_registry_is_flat_complete_and_hash_addressable(self):
        registry = surfaces.build_registry(fixture_data())
        self.assertEqual(registry['stats']['total'], len(registry['tasks']))
        self.assertEqual(registry['categories'][0]['taskCount'], 1)
        rollup = registry['categories'][0]['taskScoreRollup']
        self.assertEqual(rollup['unitOfAnalysis'], 'task')
        self.assertEqual(rollup['taskCount'], 1)
        self.assertEqual(rollup['medians'], {
            'aiExecution': 80,
            'humanAccountability': 40,
            'automationExposure': 58,
            'readiness': 70,
        })
        self.assertEqual(rollup['distributions']['aiExecution']['80-100'], 1)
        self.assertEqual(rollup['evidenceCoverage']['e0TaskCount'], 1)
        self.assertEqual(rollup['evidenceCoverage']['e1ToE4TaskCount'], 0)
        self.assertIn('not a job-replacement score', rollup['guardrail'])
        record = registry['tasks'][0]
        self.assertEqual(record['id'], 'test-a-public-page')
        self.assertEqual(record['urls']['task'],
                         'https://goodrich-dev.github.io/task-library/#task=test-a-public-page')
        self.assertEqual(record['urls']['taskPage'],
                         'https://blitzmetrics.com/test-a-public-page/')
        self.assertEqual(record['urls']['definitiveArticle'],
                         'https://blitzmetrics.com/example/')
        self.assertEqual(record['taskPageMatch'], {
            'matchMethod': 'manual-content-review',
            'canonicalTask': None,
        })
        self.assertEqual(record['skill']['mediaType'], 'text/markdown')
        self.assertEqual(record['flag'], 'review after first production run')
        fixture_source_digest = fixture_data()['categories'][0]['tasks'][0]['sourceSha256']
        self.assertEqual(record['skill']['sha256'], fixture_source_digest)
        self.assertEqual(record['skill']['digestSource'], 'resolved-source')
        self.assertEqual(record['skill']['markdownSha256'],
                         surfaces.sha256_text(record['skill']['markdown']))
        self.assertNotEqual(record['skill']['sha256'], record['skill']['markdownSha256'])
        self.assertRegex(registry['registryRevision'], r'^sha256:[a-f0-9]{64}$')

    def test_legacy_and_pathless_digest_fallbacks_are_explicit_and_deterministic(self):
        legacy = fixture_data()
        legacy_task = legacy['categories'][0]['tasks'][0]
        del legacy_task['sourceSha256']
        first = surfaces.build_registry(legacy)['tasks'][0]['skill']
        second = surfaces.build_registry(copy.deepcopy(legacy))['tasks'][0]['skill']
        self.assertEqual(first, second)
        self.assertEqual(first['digestSource'], 'legacy-catalog-content')
        self.assertEqual(first['sha256'], first['markdownSha256'])

        pathless_gap = fixture_data()
        gap = pathless_gap['categories'][0]['tasks'][0]
        gap['sourceSha256'] = None
        gap['status'] = 'gap'
        skill = surfaces.build_registry(pathless_gap)['tasks'][0]['skill']
        # Explicit null means unavailable even if a legacy presentation string
        # happens to remain; it must never fall back and look evidence-bindable.
        self.assertIsNone(skill['sha256'])
        self.assertEqual(skill['digestSource'], 'unavailable')

    def test_generation_is_deterministic(self):
        data = fixture_data()
        first = surfaces.render_outputs(data)
        second = surfaces.render_outputs(copy.deepcopy(data))
        self.assertEqual(first, second)

    def test_post_evidence_category_rollups_are_persisted_idempotently(self):
        data = fixture_data()
        self.assertNotIn('taskScoreRollup', data['categories'][0])
        self.assertTrue(surfaces.attach_category_rollups(data))
        persisted = data['categories'][0]['taskScoreRollup']
        self.assertEqual(persisted, surfaces.build_task_score_rollup(
            data['categories'][0]['tasks']
        ))
        self.assertFalse(surfaces.attach_category_rollups(data))

    def test_category_rollup_has_exact_medians_distributions_and_neutral_evidence_counts(self):
        first = {
            'slug': 'first-task',
            'capability': capability(),
            'evidence': {'effectiveEvidenceLevel': 'E0'},
        }
        second_capability = capability()
        second_capability.update({
            'aiExecution': 81,
            'humanAccountability': 61,
            'automationExposure': 19,
            'readiness': 100,
            'mode': 'Human-led + AI',
        })
        second = {
            'slug': 'second-task',
            'capability': second_capability,
            'evidence': {
                'effectiveEvidenceLevel': 'E2',
                # A negative result still establishes E2 rigor. The rollup
                # counts coverage and must not relabel it as positive proof.
                'resultInterpretation': 'does-not-support-capability',
            },
        }
        rollup = surfaces.build_task_score_rollup([first, second])
        self.assertEqual(rollup['medians'], {
            'aiExecution': 80.5,
            'humanAccountability': 50.5,
            'automationExposure': 38.5,
            'readiness': 85,
        })
        self.assertEqual(rollup['distributions']['aiExecution'], {
            '0-19': 0, '20-39': 0, '40-59': 0, '60-79': 0, '80-100': 2,
        })
        self.assertEqual(rollup['distributions']['automationExposure'], {
            '0-19': 1, '20-39': 0, '40-59': 1, '60-79': 0, '80-100': 0,
        })
        self.assertEqual(rollup['modeCounts'], {
            'Agent + reviewer': 1,
            'Human-led + AI': 1,
        })
        self.assertEqual(rollup['evidenceCoverage'], {
            'e0TaskCount': 1,
            'e1ToE4TaskCount': 1,
            'byLevel': {'E0': 1, 'E1': 0, 'E2': 1, 'E3': 0, 'E4': 0},
        })
        for field in surfaces.SCORE_FIELDS:
            self.assertEqual(sum(rollup['distributions'][field].values()), 2)

    def test_category_rollup_rejects_unknown_effective_evidence_level(self):
        task = {
            'slug': 'bad-evidence',
            'capability': capability(),
            'evidence': {'effectiveEvidenceLevel': 'E5'},
        }
        with self.assertRaisesRegex(ValueError, 'E0-E4'):
            surfaces.build_task_score_rollup([task])

    def test_registry_revision_covers_public_links(self):
        first_data = fixture_data()
        second_data = copy.deepcopy(first_data)
        second_data['bundleUrl'] = 'TaskLibrary-Skills-v2.zip'
        first = surfaces.build_registry(first_data)
        second = surfaces.build_registry(second_data)
        self.assertNotEqual(first['links']['skillBundle'], second['links']['skillBundle'])
        self.assertNotEqual(first['registryRevision'], second['registryRevision'])

    def test_duplicate_slug_is_rejected(self):
        data = fixture_data()
        duplicate_category = copy.deepcopy(data['categories'][0])
        duplicate_category['folder'] = 'second-category'
        duplicate_category['name'] = 'Second Category'
        data['categories'].append(duplicate_category)
        data['stats']['total'] = 2
        data['stats']['categories'] = 2
        with self.assertRaisesRegex(ValueError, 'duplicate task slug'):
            surfaces.build_registry(data)

    def test_source_count_drift_is_rejected(self):
        data = fixture_data()
        data['stats']['total'] = 99
        with self.assertRaisesRegex(ValueError, 'stats.total'):
            surfaces.build_registry(data)

    def test_invalid_capability_score_is_rejected(self):
        data = fixture_data()
        data['categories'][0]['tasks'][0]['capability']['aiExecution'] = 130
        with self.assertRaisesRegex(ValueError, 'aiExecution'):
            surfaces.build_registry(data)

    def test_llms_text_contains_discovery_and_guardrails(self):
        registry = surfaces.build_registry(fixture_data())
        output = surfaces.build_llms_text(registry)
        self.assertTrue(output.startswith('# BlitzMetrics Task Library\n'))
        self.assertIn('/task-registry.json', output)
        self.assertIn('/task-registry.schema.json', output)
        self.assertIn('/public-article-audit.json', output)
        self.assertIn('E0', output)
        self.assertIn('E1-E4', output)
        self.assertIn('median task scores', output)
        self.assertIn('not a job-replacement score', output)
        self.assertIn('manually reviewed exact task pages', output)
        self.assertIn('broader hub', output)
        self.assertIn('not proof that the task succeeds in production', output)

    def test_schema_contract_has_versioned_task_requirements(self):
        with open(surfaces.SCHEMA_SOURCE, encoding='utf-8') as handle:
            schema = json.load(handle)
        self.assertEqual(schema['$schema'], 'https://json-schema.org/draft/2020-12/schema')
        self.assertEqual(schema['properties']['schemaVersion']['const'], surfaces.SCHEMA_VERSION)
        required = set(schema['$defs']['task']['required'])
        self.assertTrue(
            {'id', 'slug', 'flag', 'urls', 'taskPageMatch', 'skill', 'capability', 'evidence'}
            <= required
        )
        self.assertTrue(
            {'definitiveArticles', 'tasksWithArticle', 'tasksWithoutArticle'}
            <= set(schema['properties']['stats']['required'])
        )
        self.assertEqual(schema['$defs']['task']['properties']['capability']
                         ['properties']['evidenceLevel']['pattern'], '^E[0-4]$')
        self.assertIn('taskScoreRollup', schema['$defs']['category']['required'])
        self.assertIn('taskPage', schema['$defs']['task']['properties']['urls']['required'])
        self.assertTrue(
            {'tasksWithTaskPage', 'tasksWithoutTaskPage', 'uniqueTaskPages'}
            <= set(schema['properties']['stats']['required'])
        )
        self.assertEqual(
            set(schema['$defs']['taskScoreRollup']['required']),
            {
                'unitOfAnalysis', 'taskCount', 'medians', 'distributions',
                'modeCounts', 'evidenceCoverage', 'guardrail',
            },
        )

    def test_category_ui_bundle_is_mirrored_and_exposes_rollup_guardrails(self):
        root = Path(surfaces.ROOT)
        app = (root / 'app.js').read_text(encoding='utf-8')
        dashboard_app = (root / 'dashboard' / 'app.js').read_text(encoding='utf-8')
        self.assertEqual(app, dashboard_app)
        self.assertIn('categoryTaskScoreRollup', app)
        self.assertIn('Not a job-replacement score', app)
        self.assertIn('Evidence level records evaluation rigor', app)
        self.assertIn('Exact task SOP ↗', app)
        self.assertIn('Broader definitive hub ↗', app)

    def test_article_coverage_stats_must_match_task_records(self):
        for field, bad_value in (
            ('tasksWithArticle', 0),
            ('tasksWithoutArticle', 1),
            ('definitiveArticles', 0),
        ):
            with self.subTest(field=field):
                data = fixture_data()
                data['stats'][field] = bad_value
                with self.assertRaisesRegex(ValueError, f'stats.{field}'):
                    surfaces.build_registry(data)

    def test_task_page_coverage_stats_must_match_task_records(self):
        for field, bad_value in (
            ('tasksWithTaskPage', 0),
            ('tasksWithoutTaskPage', 1),
            ('uniqueTaskPages', 0),
        ):
            with self.subTest(field=field):
                data = fixture_data()
                data['stats'][field] = bad_value
                with self.assertRaisesRegex(ValueError, f'stats.{field}'):
                    surfaces.build_registry(data)

    def test_current_task_pages_match_only_the_reviewed_map_and_aliases_count_once(self):
        root = Path(surfaces.ROOT)
        source = json.loads((root / 'build' / 'task-pages.json').read_text(encoding='utf-8'))
        with open(surfaces.DEFAULT_INPUT, encoding='utf-8') as handle:
            data = json.load(handle)
        registry = surfaces.build_registry(data)
        mapped = {
            task['slug']: task for task in registry['tasks']
            if task['urls']['taskPage']
        }
        self.assertEqual(set(mapped), set(source['tasks']))
        for slug, reviewed in source['tasks'].items():
            self.assertEqual(mapped[slug]['urls']['taskPage'], reviewed['url'])
            self.assertEqual(mapped[slug]['taskPageMatch']['matchMethod'], reviewed['matchMethod'])
            self.assertEqual(
                mapped[slug]['taskPageMatch']['canonicalTask'],
                reviewed.get('canonicalTask'),
            )
        self.assertEqual(registry['stats']['tasksWithTaskPage'], len(source['tasks']))
        self.assertEqual(
            registry['stats']['tasksWithoutTaskPage'],
            registry['stats']['total'] - len(source['tasks']),
        )
        self.assertEqual(
            registry['stats']['uniqueTaskPages'],
            len({reviewed['url'] for reviewed in source['tasks'].values()}),
        )
        alias = mapped['how-to-process-videos-via-marketscale']
        canonical = mapped['process-videos-via-marketscale']
        self.assertEqual(alias['taskPageMatch']['canonicalTask'], canonical['slug'])
        self.assertEqual(alias['urls']['taskPage'], canonical['urls']['taskPage'])

    def test_current_dashboard_payload_renders_every_registered_task(self):
        with open(surfaces.DEFAULT_INPUT, encoding='utf-8') as handle:
            data = json.load(handle)
        registry = surfaces.build_registry(data)
        self.assertEqual(len(registry['tasks']), data['stats']['total'])
        self.assertEqual(len({task['slug'] for task in registry['tasks']}), len(registry['tasks']))
        self.assertEqual(sum(category['taskCount'] for category in registry['categories']),
                         len(registry['tasks']))
        for task in registry['tasks']:
            self.assertEqual(bool(task['skill']['markdown'].strip()), task['skill']['runnable'])
            if task['skill']['digestSource'] == 'unavailable':
                self.assertIsNone(task['skill']['sha256'])
            else:
                self.assertRegex(task['skill']['sha256'], r'^[a-f0-9]{64}$')
            self.assertRegex(task['skill']['markdownSha256'], r'^[a-f0-9]{64}$')

    def test_built_catalog_preserves_exact_trailing_newline_source_digest(self):
        slug = 'create-social-media-posts-per-platform'
        source_path = (Path(surfaces.ROOT) / 'skills' / 'content-factory-process' /
                       f'{slug}.md')
        source_text = source_path.read_text(encoding='utf-8')
        self.assertTrue(source_text.endswith('\n'))
        with open(surfaces.DEFAULT_INPUT, encoding='utf-8') as handle:
            data = json.load(handle)
        catalog_task = next(
            task for category in data['categories'] for task in category['tasks']
            if task['slug'] == slug
        )
        self.assertEqual(catalog_task['sourceSha256'], surfaces.sha256_text(source_text))
        self.assertNotEqual(catalog_task['sourceSha256'],
                            surfaces.sha256_text(catalog_task['content']))
        registry_task = next(
            task for task in surfaces.build_registry(data)['tasks'] if task['slug'] == slug
        )
        self.assertEqual(registry_task['skill']['sha256'], catalog_task['sourceSha256'])
        self.assertEqual(registry_task['skill']['digestSource'], 'resolved-source')

    def test_current_registry_conforms_to_the_published_schema(self):
        with open(surfaces.DEFAULT_INPUT, encoding='utf-8') as handle:
            registry = surfaces.build_registry(json.load(handle))
        with open(surfaces.SCHEMA_SOURCE, encoding='utf-8') as handle:
            schema = json.load(handle)
        self.assertEqual(schema_validator.schema_errors(registry, schema, schema), [])


if __name__ == '__main__':
    unittest.main()
