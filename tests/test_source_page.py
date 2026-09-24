import unittest
from unittest.mock import Mock

from collector.source_page import load_scrolled_candidates


class SourcePageTests(unittest.TestCase):
    def test_available_candidate_limit_skips_scrolling(self):
        candidates = Mock()
        candidates.count.return_value = 3
        collector = Mock()
        collector.get_post_candidates.return_value = candidates
        scroller = Mock()

        result = load_scrolled_candidates(
            Mock(), scroller, collector, candidate_limit=1
        )

        self.assertIs(result, candidates)
        scroller.scroll.assert_not_called()

    def test_scroll_receives_live_candidate_stop_condition(self):
        candidates = Mock()
        candidates.count.side_effect = [0, 2]
        collector = Mock()
        collector.get_post_candidates.return_value = candidates
        scroller = Mock()
        page = Mock()

        load_scrolled_candidates(page, scroller, collector, candidate_limit=2)

        stop_when = scroller.scroll.call_args.kwargs["stop_when"]
        self.assertTrue(stop_when())

    def test_empty_search_results_do_not_scroll(self):
        candidates = Mock()
        candidates.count.return_value = 0
        collector = Mock()
        collector.get_post_candidates.return_value = candidates
        scroller = Mock()

        result = load_scrolled_candidates(
            Mock(), scroller, collector,
            skip_scroll_when_empty=True,
            candidate_limit=1,
        )

        self.assertIs(result, candidates)
        scroller.scroll.assert_not_called()


if __name__ == "__main__":
    unittest.main()
