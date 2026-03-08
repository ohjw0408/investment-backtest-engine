from modules.analyzer.retirement_analyzer import RetirementAnalyzer


class SafeWithdrawalEngine:

    def __init__(self):
        pass

    # -------------------------------------------------
    # Safe withdrawal finder
    # -------------------------------------------------

    def find_safe_withdrawal(
        self,
        history,
        initial_capital,
        years,
        inflation=0.0,
        target_success_rate=0.9,
        tolerance=1e-2,
        max_iter=40
    ):

        # -----------------------------
        # search range
        # -----------------------------

        low = 0

        high = initial_capital / (years * 12)

        best_withdrawal = 0
        best_success_rate = 0

        # -----------------------------
        # binary search
        # -----------------------------

        for _ in range(max_iter):

            guess = (low + high) / 2

            analyzer = RetirementAnalyzer(
                monthly_withdrawal=guess,
                years=years,
                inflation=inflation
            )

            result = analyzer.analyze(
                history,
                initial_capital
            )

            success_rate = result["success_rate"]

            # -----------------------------
            # success
            # -----------------------------

            if success_rate >= target_success_rate:

                best_withdrawal = guess
                best_success_rate = success_rate

                low = guess

            else:

                high = guess

            # -----------------------------
            # convergence
            # -----------------------------

            if abs(high - low) < tolerance:
                break

        return {

            "safe_monthly_withdrawal": best_withdrawal,

            "success_rate": best_success_rate

        }