from rouge_score import rouge_scorer
from core.llm_client import llm
from core.logger import logger


class InsightEvaluator:
    """
    Implements InsightEval evaluation framework:
    - Insight Recall (ground truth coverage)
    - Insight Precision (generated insight accuracy)
    - Insight F1 (harmonic mean)
    - Novelty Score (unannotated insight discovery)
    """

    def __init__(self):
        self.rouge = rouge_scorer.RougeScorer(["rouge1", "rougeL"], use_stemmer=True)

    def evaluate(self, insights: list) -> list:
        """
        Filter and deduplicate a list of insight dicts from InsightDiscoverer.
        Removes failed discoveries (stats.name == 'error') and near-duplicate
        insights (ROUGE-1 similarity > 0.85 between insight texts).
        Returns the cleaned list for downstream summarisation.
        """
        # Drop failed discoveries
        valid = [i for i in insights if i.get("stats", {}).get("name") != "error" and i.get("insight")]

        # Deduplicate by insight text similarity
        unique: list = []
        for item in valid:
            text = item.get("insight", "")
            is_dup = any(
                self._similarity(text, u.get("insight", "")) > 0.85 for u in unique
            )
            if not is_dup:
                unique.append(item)

        return unique

    def compute_all(self, generated: list, ground_truth: list) -> dict:
        recall = self.compute_recall(generated, ground_truth)
        precision = self.compute_precision(generated, ground_truth)
        f1 = self._harmonic_mean(recall, precision)
        novelty = self.compute_novelty(generated, ground_truth)
        return {
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "f1": round(f1, 4),
            "novelty": round(novelty, 4),
        }

    def compute_recall(self, generated: list, ground_truth: list) -> float:
        """For each GT insight, find best matching generated insight."""
        if not ground_truth or not generated:
            return 0.0
        scores = []
        for gt in ground_truth:
            best = max(self._similarity(gt, g) for g in generated)
            scores.append(best)
        return sum(scores) / len(scores)

    def compute_precision(self, generated: list, ground_truth: list) -> float:
        """For each generated insight, find best matching GT insight."""
        if not ground_truth or not generated:
            return 0.0
        scores = []
        for g in generated:
            best = max(self._similarity(g, gt) for gt in ground_truth)
            scores.append(best)
        return sum(scores) / len(scores)

    def compute_novelty(self, generated: list, ground_truth: list) -> float:
        """Identify novel insights not present in ground truth."""
        if not generated:
            return 0.0
        novel = 0
        precision_count = 0

        for g in generated:
            best_match = max(
                (self._similarity(g, gt) for gt in ground_truth), default=0.0
            )
            if best_match >= 0.4:
                precision_count += 1
            else:
                if self._llm_verify_novelty(g, ground_truth):
                    novel += 1

        return (precision_count + novel) / max(len(generated), 1)

    def _similarity(self, text1: str, text2: str) -> float:
        """ROUGE-1 F1 similarity between two texts."""
        try:
            scores = self.rouge.score(text1, text2)
            return scores["rouge1"].fmeasure
        except Exception:
            return 0.0

    def _harmonic_mean(self, a: float, b: float) -> float:
        if a + b == 0:
            return 0.0
        return 2 * a * b / (a + b)

    def _llm_verify_novelty(self, insight: str, ground_truth: list) -> bool:
        """Ask LLM if this insight represents genuinely new knowledge."""
        gt_str = "\n".join(f"- {g}" for g in ground_truth[:5])
        prompt = f"""Does this insight reveal new information not captured in the reference insights?
New insight: {insight}
Reference insights:
{gt_str}

Answer 'yes' if novel, 'no' if duplicate. One word only."""
        try:
            resp = llm.chat(prompt, temperature=0.0).strip().lower()
            return "yes" in resp
        except Exception:
            return False
