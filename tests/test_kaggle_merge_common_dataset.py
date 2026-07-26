"""Tests for common dataset normalization helpers."""

from scripts.kaggle_merge_common_dataset import normalize_title_key, strip_markup


def test_strip_markup_removes_scholarly_title_tags():
    title = (
        "Cohabitation and<i>Ekageikama</i>in the<scp>K</scp>andyan"
        "<scp>K</scp>ingdom (<scp>S</scp>ri<scp>L</scp>anka)"
    )

    assert strip_markup(title) == "Cohabitation and Ekageikama in the Kandyan Kingdom (Sri Lanka)"


def test_strip_markup_decodes_entities_and_escaped_tags():
    title = (
        "Fired-Siltstone Based Geopolymers for CO&lt;inf&gt;2&lt;/inf&gt; "
        "Sequestration Wells &amp; Storage"
    )

    assert strip_markup(title) == "Fired-Siltstone Based Geopolymers for CO2 Sequestration Wells & Storage"


def test_strip_markup_decodes_nested_and_source_typo_entities():
    abstract = "Oliver&amp;amp;Pharr method and &squo;Gibson' soil"

    assert strip_markup(abstract) == "Oliver&Pharr method and 'Gibson' soil"


def test_normalize_title_key_uses_cleaned_markup():
    title = "<scp>I</scp>slam and Gender"

    assert normalize_title_key(title) == "islam and gender"
