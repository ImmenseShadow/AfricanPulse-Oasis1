import unittest

from src.processors.categorizer import categorize


class CategorizerTests(unittest.TestCase):
    def test_clear_matches(self):
        self.assertEqual(categorize("Nigerian fintech startup raises funding for mobile app"), "Technology")
        self.assertEqual(categorize("Ghana universities launch scholarship programme for students"), "Education")
        self.assertEqual(categorize("Health ministry confirms cholera outbreak in hospital"), "Health")

    def test_unknown_text_is_uncategorized(self):
        self.assertEqual(categorize("A quiet afternoon"), "Uncategorized")
        self.assertEqual(categorize("", None), "Uncategorized")

    def test_tie_is_uncategorized(self):
        self.assertEqual(categorize("Election results lift market"), "Uncategorized")

    def test_weak_evidence_is_uncategorized(self):
        self.assertEqual(categorize("Local news", "The school opened."), "Uncategorized")

    def test_summary_can_add_evidence(self):
        self.assertEqual(
            categorize("Local update", "The school and the university announced exams."), "Education"
        )

    def test_whole_words_only(self):
        self.assertEqual(categorize("Said the captain"), "Uncategorized")  # "ai" inside "Said"

    def test_custom_rules(self):
        self.assertEqual(categorize("Jollof festival", rules={"Culture": ("jollof",)}), "Culture")


if __name__ == "__main__":
    unittest.main()
