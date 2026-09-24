import tempfile
import unittest
from pathlib import Path

from config.config_loader import (
    DiscoveryConfigError,
    load_discovery_sources,
    load_keywords,
)
from config.discovery_source import DiscoverySourceType


class DiscoveryConfigTests(unittest.TestCase):
    def write_config(self, content):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "keywords.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_structured_config_loads_normalized_enabled_sources(self):
        path = self.write_config("""
discovery:
  keywords:
    - value: "  AI   Agents  "
      enabled: true
  hashtags:
    - value: "#AgenticAI"
      enabled: true
  creators:
    - name: Jane Doe
      profile_url: https://linkedin.com/in/jane-doe/?trk=profile
      enabled: true
  companies:
    - name: Example Inc
      page_url: http://www.linkedin.com/company/example-inc#about
      enabled: true
""")

        sources = load_discovery_sources(path)

        self.assertEqual([source.source_type for source in sources], [
            DiscoverySourceType.KEYWORD,
            DiscoverySourceType.HASHTAG,
            DiscoverySourceType.CREATOR,
            DiscoverySourceType.COMPANY,
        ])
        self.assertEqual(sources[0].value, "AI Agents")
        self.assertEqual(sources[1].value, "AgenticAI")
        self.assertEqual(sources[2].url, "https://www.linkedin.com/in/jane-doe/")
        self.assertEqual(sources[3].url, "https://www.linkedin.com/company/example-inc/")

    def test_legacy_keywords_remain_supported(self):
        path = self.write_config("keywords:\n  - SaaS\n  - AI Agents\n")
        self.assertEqual(load_keywords(path), ["SaaS", "AI Agents"])

    def test_disabled_sources_are_excluded(self):
        path = self.write_config("""
discovery:
  keywords:
    - value: SaaS
      enabled: true
    - value: Startups
      enabled: false
  hashtags:
    - value: saas
      enabled: false
""")
        self.assertEqual(load_keywords(path), ["SaaS"])
        self.assertEqual(len(load_discovery_sources(path)), 1)

    def test_sources_are_deduplicated_without_reordering(self):
        path = self.write_config("""
discovery:
  keywords:
    - value: SaaS
    - value: saas
    - value: FinTech
  hashtags:
    - value: "#AI"
    - value: ai
""")
        sources = load_discovery_sources(path)
        self.assertEqual(
            [(source.source_type.value, source.value) for source in sources],
            [("keyword", "SaaS"), ("keyword", "FinTech"), ("hashtag", "AI")],
        )

    def test_invalid_linkedin_urls_are_rejected(self):
        invalid_configs = (
            """
discovery:
  creators:
    - name: Jane
      profile_url: https://example.com/in/jane/
""",
            """
discovery:
  creators:
    - name: Jane
      profile_url: https://www.linkedin.com/company/jane/
""",
            """
discovery:
  companies:
    - name: Example
      page_url: https://www.linkedin.com/in/example/
""",
        )
        for content in invalid_configs:
            with self.subTest(content=content):
                with self.assertRaises(DiscoveryConfigError):
                    load_discovery_sources(self.write_config(content))

    def test_missing_and_empty_required_fields_are_rejected(self):
        invalid_configs = (
            "discovery:\n  keywords:\n    - enabled: true\n",
            "discovery:\n  hashtags:\n    - value: '   '\n",
            "discovery:\n  creators:\n    - name: Jane\n",
        )
        for content in invalid_configs:
            with self.subTest(content=content):
                with self.assertRaises(DiscoveryConfigError):
                    load_discovery_sources(self.write_config(content))

    def test_unknown_source_sections_are_rejected(self):
        path = self.write_config("discovery:\n  topics: []\n")
        with self.assertRaisesRegex(DiscoveryConfigError, "Unsupported discovery source"):
            load_discovery_sources(path)

    def test_unknown_root_fields_and_mixed_formats_are_rejected(self):
        invalid_configs = (
            "discover:\n  keywords: []\n",
            "discovery:\n  keywords: []\nkeywords:\n  - SaaS\n",
        )
        for content in invalid_configs:
            with self.subTest(content=content):
                with self.assertRaises(DiscoveryConfigError):
                    load_discovery_sources(self.write_config(content))

    def test_project_config_preserves_existing_keyword_search(self):
        self.assertEqual(load_keywords(), ["SaaS", "AI Agents"])


if __name__ == "__main__":
    unittest.main()
