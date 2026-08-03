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
        record = registry['tasks'][0]
        self.assertEqual(record['id'], 'test-a-public-page')
        self.assertEqual(record['urls']['task'],
                         'https://goodrich-dev.github.io/task-library/#task=test-a-public-page')
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
        self.assertIn('E0', output)
        self.assertIn('not proof that the task succeeds in production', output)

    def test_schema_contract_has_versioned_task_requirements(self):
        with open(surfaces.SCHEMA_SOURCE, encoding='utf-8') as handle:
            schema = json.load(handle)
        self.assertEqual(schema['$schema'], 'https://json-schema.org/draft/2020-12/schema')
        self.assertEqual(schema['properties']['schemaVersion']['const'], surfaces.SCHEMA_VERSION)
        required = set(schema['$defs']['task']['required'])
        self.assertTrue({'id', 'slug', 'flag', 'urls', 'skill', 'capability', 'evidence'} <= required)
        self.assertEqual(schema['$defs']['task']['properties']['capability']
                         ['properties']['evidenceLevel']['pattern'], '^E[0-4]$')

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
