import pandas as pd
import numpy as np
from typing import Tuple

class EquivalenceOracle:
    """Unified oracle for dataframe comparison across all SRE runners."""

    @staticmethod
    def check_equivalence(df_cand: pd.DataFrame, df_true: pd.DataFrame, rtol: float = 1e-4, atol: float = 1e-4) -> Tuple[bool, float]:
        """
        Determines if two dataframes are equivalent using order-insensitive, null-safe canonical sorting,
        followed by a strict assert_frame_equal with configurable relative/absolute tolerances.
        
        Args:
            df_cand: The candidate (mutated) dataframe
            df_true: The baseline (true) dataframe
            rtol: Relative tolerance for float comparisons (default 1e-4, i.e. 0.01%)
            atol: Absolute tolerance for float comparisons (default 1e-4)
            
        Returns:
            is_equivalent: bool
            variance_pct: float (heuristic variance for logging if not equivalent)
        """
        if df_cand is None or df_true is None:
            return False, 100.0
        if df_cand.empty and df_true.empty:
            return True, 0.0
        if df_cand.empty != df_true.empty:
            return False, 100.0
        if len(df_cand) != len(df_true) or df_cand.shape[1] != df_true.shape[1]:
            # Quick structural mismatch check
            return False, 100.0

        is_equiv = False
        try:
            # 1. Generate canonical tuples for robust sorting
            def canonical_row(row, cols):
                items = []
                for c in cols:
                    val = row[c]
                    if pd.isna(val) or val is None:
                        items.append(f"{c}:__NULL__")
                    elif isinstance(val, (int, float, np.number)):
                        # Round purely for stable string sorting, not for the final assertion
                        rounded = round(float(val), 4)
                        items.append(f"{c}:{rounded}")
                    else:
                        items.append(f"{c}:{str(val).strip()}")
                return tuple(items)

            c_cols = sorted(df_cand.columns) if set(df_cand.columns) == set(df_true.columns) else list(df_cand.columns)
            t_cols = sorted(df_true.columns) if set(df_cand.columns) == set(df_true.columns) else list(df_true.columns)

            c_rows_tuples = [canonical_row(row, c_cols) for _, row in df_cand.iterrows()]
            t_rows_tuples = [canonical_row(row, t_cols) for _, row in df_true.iterrows()]

            # 2. Get sorted index order
            c_indices = sorted(range(len(df_cand)), key=lambda i: c_rows_tuples[i])
            t_indices = sorted(range(len(df_true)), key=lambda i: t_rows_tuples[i])

            # 3. Sort DataFrames and reset index
            df_cand_sorted = df_cand.iloc[c_indices].reset_index(drop=True)
            df_true_sorted = df_true.iloc[t_indices].reset_index(drop=True)
            
            # Reorder columns to match baseline
            df_cand_sorted = df_cand_sorted[df_true_sorted.columns]

            # 4. Strict assertion with numeric tolerance
            pd.testing.assert_frame_equal(df_true_sorted, df_cand_sorted, check_dtype=False, rtol=rtol, atol=atol)
            is_equiv = True
        except AssertionError:
            is_equiv = False
        except Exception:
            is_equiv = False

        # Calculate heuristic variance_pct for reporting
        variance_pct = 0.0
        base_rows = len(df_true)
        mut_rows = len(df_cand)
        row_delta = mut_rows - base_rows
        
        if not is_equiv:
            if base_rows == mut_rows and list(df_true.columns) == list(df_cand.columns):
                try:
                    numeric_cols = df_true.select_dtypes(include=["number"]).columns
                    if len(numeric_cols) > 0:
                        base_sum = float(df_true[numeric_cols].sum().sum())
                        mut_sum = float(df_cand[numeric_cols].sum().sum())
                        if base_sum != 0:
                            variance_pct = abs(mut_sum - base_sum) / abs(base_sum) * 100.0
                        else:
                            variance_pct = 100.0 if mut_sum != 0 else 0.0
                except Exception:
                    pass
            else:
                variance_pct = abs(row_delta) / (base_rows if base_rows > 0 else 1.0) * 100.0

        return is_equiv, variance_pct
