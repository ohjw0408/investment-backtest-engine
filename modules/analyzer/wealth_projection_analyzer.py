import numpy as np


class WealthProjectionAnalyzer:
    """
    Wealth Projection Analyzer

    RollingScenarioAnalyzer가 생성한
    wealth multiple distribution을 분석한다.

    반환값은 다음을 포함한다.

    - raw distribution
    - summary statistics
    - percentiles
    - distribution shape metrics
    """

    def analyze(self, wealth_distribution):

        dist = np.array(wealth_distribution, dtype=float)

        if dist.size == 0:
            raise ValueError("wealth distribution is empty")

        # -------------------------------------------------
        # Summary statistics
        # -------------------------------------------------

        mean = np.mean(dist)
        median = np.median(dist)
        std = np.std(dist)
        variance = np.var(dist)

        # -------------------------------------------------
        # Percentiles
        # -------------------------------------------------

        percentiles = {
            "p1": np.percentile(dist, 1),
            "p5": np.percentile(dist, 5),
            "p10": np.percentile(dist, 10),
            "p25": np.percentile(dist, 25),
            "p50": np.percentile(dist, 50),
            "p75": np.percentile(dist, 75),
            "p90": np.percentile(dist, 90),
            "p95": np.percentile(dist, 95),
            "p99": np.percentile(dist, 99),
        }

        # -------------------------------------------------
        # Distribution shape metrics
        # -------------------------------------------------

        centered = dist - mean

        m3 = np.mean(centered ** 3)
        m4 = np.mean(centered ** 4)

        skewness = m3 / (std ** 3) if std > 0 else 0
        kurtosis = m4 / (std ** 4) if std > 0 else 0

        # -------------------------------------------------
        # Best / Worst
        # -------------------------------------------------

        best = np.max(dist)
        worst = np.min(dist)

        # -------------------------------------------------
        # Result structure
        # -------------------------------------------------

        result = {

            # raw distribution
            "distribution": dist,

            # scenario count
            "scenario_count": dist.size,

            # summary
            "summary": {
                "mean": mean,
                "median": median,
                "std": std,
                "variance": variance
            },

            # percentiles
            "percentiles": percentiles,

            # extremes
            "extremes": {
                "best": best,
                "worst": worst
            },

            # distribution shape
            "shape": {
                "skewness": skewness,
                "kurtosis": kurtosis
            }
        }

        return result