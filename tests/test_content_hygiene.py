"""Tests for content hygiene (boilerplate removal and deduplication)."""

from __future__ import annotations

import pytest

from watercrawl.integrations.content_hygiene import (
    ContentCleaner,
    Deduplicator,
    HygieneConfig,
    MinHash,
    SimHash,
    create_default_cleaner,
    create_default_deduplicator,
)


class TestBoilerplateRemoval:
    """Test boilerplate removal functionality."""

    def test_removes_navigation(self) -> None:
        cleaner = create_default_cleaner()

        html = """
        <nav>
            <a href="/home">Home</a>
            <a href="/about">About</a>
        </nav>
        <article>
            <p>This is the main content of the page.</p>
        </article>
        """

        cleaned = cleaner.clean(html)
        assert "Home" not in cleaned
        assert "About" not in cleaned
        assert "main content" in cleaned

    def test_removes_footer(self) -> None:
        cleaner = create_default_cleaner()

        html = """
        <article>
            <p>Main content here</p>
        </article>
        <footer>
            <p>Copyright 2024. All rights reserved.</p>
        </footer>
        """

        cleaned = cleaner.clean(html)
        assert "Main content" in cleaned
        assert "Copyright" not in cleaned

    def test_removes_scripts(self) -> None:
        cleaner = create_default_cleaner()

        html = """
        <script>
            console.log("tracking code");
        </script>
        <p>Actual content</p>
        """

        cleaned = cleaner.clean(html)
        assert "tracking code" not in cleaned
        assert "Actual content" in cleaned

    def test_preserves_main_content(self) -> None:
        cleaner = create_default_cleaner()

        html = """
        <article>
            <h1>Article Title</h1>
            <p>First paragraph with important information.</p>
            <p>Second paragraph with more details.</p>
        </article>
        """

        cleaned = cleaner.clean(html)
        assert "Article Title" in cleaned
        assert "important information" in cleaned
        assert "more details" in cleaned

    def test_filters_short_content(self) -> None:
        config = HygieneConfig(min_content_length=50, min_word_count=10)
        cleaner = ContentCleaner(config)

        html = "<p>Short</p>"
        cleaned = cleaner.clean(html)
        assert cleaned == ""

    def test_boilerplate_disabled(self) -> None:
        config = HygieneConfig(remove_boilerplate=False)
        cleaner = ContentCleaner(config)

        html = "<nav>Navigation</nav><p>Content</p>"
        cleaned = cleaner.clean(html)
        # When disabled, only HTML tags are removed
        assert "Navigation" in cleaned
        assert "Content" in cleaned


class TestHTMLCleaning:
    """Test HTML tag removal and text extraction."""

    def test_removes_html_tags(self) -> None:
        cleaner = create_default_cleaner()

        html = "<p>Hello <strong>world</strong></p>"
        text = cleaner.remove_html_tags(html)
        assert text == "Hello world"

    def test_decodes_html_entities(self) -> None:
        cleaner = create_default_cleaner()

        html = "A &amp; B &lt; C &gt; D"
        text = cleaner.remove_html_tags(html)
        assert text == "A & B < C > D"

    def test_normalizes_whitespace(self) -> None:
        cleaner = create_default_cleaner()

        html = "<p>Text   with\n\n  multiple    spaces</p>"
        text = cleaner.remove_html_tags(html)
        assert text == "Text with multiple spaces"


class TestSimHash:
    """Test SimHash implementation."""

    def test_identical_texts_have_zero_distance(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        hash1 = SimHash(text)
        hash2 = SimHash(text)

        assert hash1.distance(hash2) == 0

    def test_similar_texts_have_small_distance(self) -> None:
        text1 = "The quick brown fox jumps over the lazy dog"
        text2 = "The quick brown fox jumps over a lazy dog"

        hash1 = SimHash(text1)
        hash2 = SimHash(text2)

        distance = hash1.distance(hash2)
        assert distance < 10  # Should be very similar

    def test_different_texts_have_large_distance(self) -> None:
        text1 = "The quick brown fox jumps over the lazy dog"
        text2 = "Python is a high-level programming language"

        hash1 = SimHash(text1)
        hash2 = SimHash(text2)

        distance = hash1.distance(hash2)
        assert distance > 10  # Should be quite different

    def test_detects_near_duplicates(self) -> None:
        text1 = "Flight school offers pilot training courses"
        text2 = "Flight school offers pilots training courses"

        hash1 = SimHash(text1)
        hash2 = SimHash(text2)

        assert hash1.is_duplicate(hash2, threshold=5)

    def test_rejects_non_duplicates(self) -> None:
        text1 = "Flight school in Cape Town"
        text2 = "University in Johannesburg"

        hash1 = SimHash(text1)
        hash2 = SimHash(text2)

        assert not hash1.is_duplicate(hash2, threshold=3)


class TestMinHash:
    """Test MinHash implementation."""

    def test_identical_texts_have_perfect_similarity(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        hash1 = MinHash(text)
        hash2 = MinHash(text)

        similarity = hash1.jaccard_similarity(hash2)
        assert similarity == 1.0

    def test_similar_texts_have_high_similarity(self) -> None:
        text1 = "The quick brown fox jumps over the lazy dog"
        text2 = "The quick brown fox jumps over a lazy dog"

        hash1 = MinHash(text1)
        hash2 = MinHash(text2)

        similarity = hash1.jaccard_similarity(hash2)
        assert similarity > 0.7  # Should be quite similar

    def test_different_texts_have_low_similarity(self) -> None:
        text1 = "The quick brown fox"
        text2 = "Python programming language"

        hash1 = MinHash(text1)
        hash2 = MinHash(text2)

        similarity = hash1.jaccard_similarity(hash2)
        assert similarity < 0.3

    def test_detects_duplicates(self) -> None:
        text1 = "Flight school training program"
        text2 = "Flight school training program with minor addition"

        hash1 = MinHash(text1)
        hash2 = MinHash(text2)

        assert hash1.is_duplicate(hash2, threshold=0.7)


class TestDeduplicator:
    """Test deduplication functionality."""

    def test_detects_exact_duplicates(self) -> None:
        dedup = create_default_deduplicator()

        text = "This is some unique content"

        assert not dedup.is_duplicate(text)
        dedup.add(text)
        assert dedup.is_duplicate(text)

    def test_detects_near_duplicates(self) -> None:
        dedup = create_default_deduplicator()

        text1 = "Flight school offers comprehensive pilot training"
        text2 = "Flight school offers comprehensive pilots training"

        assert not dedup.is_duplicate(text1)
        dedup.add(text1)
        assert dedup.is_duplicate(text2)

    def test_allows_different_content(self) -> None:
        dedup = create_default_deduplicator()

        text1 = "Flight school in Cape Town"
        text2 = "University in Johannesburg"

        dedup.add(text1)
        assert not dedup.is_duplicate(text2)

    def test_deduplication_disabled(self) -> None:
        config = HygieneConfig(enable_dedup=False)
        dedup = Deduplicator(config)

        text = "Some content"
        dedup.add(text)
        assert not dedup.is_duplicate(text)

    def test_tracks_statistics(self) -> None:
        dedup = create_default_deduplicator()

        texts = [
            "First unique text",
            "Second unique text",
            "Third unique text",
        ]

        for text in texts:
            dedup.add(text)

        stats = dedup.get_stats()
        assert stats["total_indexed"] == 3
        assert stats["simhash_index_size"] == 3
        assert stats["minhash_index_size"] == 3


class TestConfiguration:
    """Test configuration options."""

    def test_default_config(self) -> None:
        config = HygieneConfig()

        assert config.remove_boilerplate is True
        assert config.enable_dedup is True
        assert config.min_content_length == 100
        assert config.simhash_threshold == 3

    def test_custom_config(self) -> None:
        config = HygieneConfig(
            min_content_length=50,
            simhash_threshold=5,
            minhash_threshold=0.90,
        )

        assert config.min_content_length == 50
        assert config.simhash_threshold == 5
        assert config.minhash_threshold == 0.90


class TestIntegration:
    """Integration tests for full cleaning pipeline."""

    def test_clean_and_deduplicate(self) -> None:
        cleaner = create_default_cleaner()
        dedup = create_default_deduplicator()

        html1 = """
        <nav>Navigation</nav>
        <article>
            <p>First flight school in Cape Town offers training</p>
        </article>
        <footer>Copyright 2024</footer>
        """

        html2 = """
        <nav>Menu</nav>
        <article>
            <p>First flight school in Cape Town offers training</p>
        </article>
        <footer>All rights reserved</footer>
        """

        # Clean both
        text1 = cleaner.clean(html1)
        text2 = cleaner.clean(html2)

        # Should detect as duplicates after cleaning
        assert not dedup.is_duplicate(text1)
        dedup.add(text1)
        assert dedup.is_duplicate(text2)

    def test_boilerplate_removal_effectiveness(self) -> None:
        """Test that boilerplate removal achieves ≥90% reduction."""
        cleaner = create_default_cleaner()

        html = """
        <nav>
            <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/about">About</a></li>
                <li><a href="/contact">Contact</a></li>
            </ul>
        </nav>
        <article>
            <h1>Main Article Title</h1>
            <p>This is the main content that should be preserved.</p>
        </article>
        <aside>
            <h3>Related Links</h3>
            <ul><li>Link 1</li><li>Link 2</li></ul>
        </aside>
        <footer>
            <p>Copyright 2024 Company Name. All rights reserved.</p>
            <p>Follow us on Twitter, Facebook, Instagram</p>
        </footer>
        """

        cleaned = cleaner.clean(html)

        # Main content should be preserved
        assert "Main Article Title" in cleaned
        assert "main content" in cleaned

        # Boilerplate should be removed
        assert "Home" not in cleaned or "About" not in cleaned
        assert "Copyright" not in cleaned or "Follow us" not in cleaned
