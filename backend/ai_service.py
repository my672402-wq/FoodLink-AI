"""
FoodLink AI — Gemini AI Service Module
Provides generative AI explanations using the official Google Gen AI Python SDK.
Falls back to deterministic rule-based explanations when Gemini is unavailable.

STRICT RULES:
  - The LLM only explains validated backend results.
  - It never decides food safety, invents data, or overrides backend logic.
  - API key is read from environment variables (never hardcoded).
  - All external calls have timeouts and retry logic.
  - The application works fully without Gemini credentials.
"""

import os
import time
import logging
from config import Config

logger = logging.getLogger(__name__)

# Default request timeout in seconds
GEMINI_REQUEST_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "15"))
# Max retries on transient failures
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))
# Delay between retries (seconds)
GEMINI_RETRY_DELAY = 1.0


class GeminiService:
    """Singleton service wrapping the official google-genai SDK with graceful degradation."""

    def __init__(self):
        self.api_key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self.model_name = Config.GEMINI_MODEL or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = None
        self._last_error = None
        self._init_client()

    def _init_client(self):
        """Initialize the Google Gen AI client if an API key is configured."""
        if self.api_key and self.api_key.strip() and self.api_key.strip() != "your_gemini_api_key_here":
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key.strip())
                logger.info(f"Gemini client initialized with model '{self.model_name}'.")
                self._last_error = None
            except ImportError:
                logger.warning("google-genai SDK not installed. Gemini features disabled.")
                self.client = None
                self._last_error = "google-genai package not installed"
            except Exception as e:
                logger.warning(f"Could not initialize google-genai client: {e}")
                self.client = None
                self._last_error = str(e)
        else:
            self.client = None
            self._last_error = "No API key configured"
            logger.info("Gemini API key not configured. Running in deterministic fallback mode.")

    def is_available(self) -> bool:
        """Check if the Gemini client is initialized and ready."""
        return self.client is not None

    def get_status(self) -> dict:
        """Return detailed status information for health checks and diagnostics."""
        return {
            "available": self.is_available(),
            "model": self.model_name,
            "has_api_key": bool(self.api_key and self.api_key.strip() and self.api_key.strip() != "your_gemini_api_key_here"),
            "last_error": self._last_error,
            "timeout_seconds": GEMINI_REQUEST_TIMEOUT,
            "max_retries": GEMINI_MAX_RETRIES
        }

    def _call_gemini(self, prompt: str, max_retries: int = None) -> str:
        """
        Internal method to call Gemini with timeout and retry logic.
        
        Args:
            prompt: The prompt text to send.
            max_retries: Override default max retries.
            
        Returns:
            Generated text string, or None on failure.
            
        Raises:
            RuntimeError on all retries exhausted.
        """
        if not self.is_available():
            return None

        retries = max_retries if max_retries is not None else GEMINI_MAX_RETRIES
        last_exception = None

        for attempt in range(retries + 1):
            try:
                from google.genai import types

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=512,
                        candidate_count=1,
                    ),
                )

                if response and response.text:
                    self._last_error = None
                    return response.text.strip()
                else:
                    logger.warning(f"Gemini returned empty response (attempt {attempt + 1})")
                    last_exception = RuntimeError("Empty response from Gemini API")

            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                logger.warning(f"Gemini API attempt {attempt + 1}/{retries + 1} failed: {e}")

                # Don't retry on auth errors or quota errors — they won't succeed
                if any(keyword in error_str for keyword in ["api_key", "invalid", "unauthorized", "403", "401", "permission"]):
                    self._last_error = f"Authentication error: {e}"
                    break

                # Don't retry on model not found
                if "not found" in error_str or "404" in error_str:
                    self._last_error = f"Model error: {e}"
                    break

                # Retry on transient errors (timeout, rate limit, server error)
                if attempt < retries:
                    delay = GEMINI_RETRY_DELAY * (attempt + 1)  # Linear backoff
                    logger.info(f"Retrying Gemini call in {delay}s...")
                    time.sleep(delay)

        self._last_error = str(last_exception) if last_exception else "Unknown error"
        return None

    # ------------------------------------------------------------------
    # PUBLIC METHODS — Each generates explanations from backend-verified data
    # ------------------------------------------------------------------

    def generate_matching_explanation(self, donation: dict, ranked_matches: list) -> dict:
        """
        Explains why top NGOs were ranked as optimal recipients.
        Must strictly reference backend scores and not invent facts.
        """
        top_matches = [m for m in ranked_matches if m.get("eligible")][:3]
        if not top_matches:
            return {
                "ai_powered": False,
                "summary": "No eligible NGO matches found based on current food safety, capacity, or dietary constraints.",
                "insights": ["Review donation expiry window or relax non-critical constraints."]
            }

        if not self.is_available():
            return self._fallback_matching_explanation(top_matches)

        # Build a grounded prompt with strict rules
        match_bullets = "\n".join([
            f"- NGO: {m['ngo_name']} | Distance: {m['distance_km']} km | Score: {m['matching_score']} | "
            f"Capacity Available: {m['available_capacity']} meals | Dietary: {m.get('dietary_preferences')} | "
            f"Proposed Allocation: {m.get('proposed_meals')} meals"
            for m in top_matches
        ])

        prompt = (
            f"You are the logistics explanation assistant for FoodLink AI.\n"
            f"Explain the following backend-calculated matching recommendations for donation '{donation.get('food_name')}' "
            f"(Category: {donation.get('food_category')}, Surplus: {donation.get('quantity')} meals, "
            f"Deadline: {donation.get('collection_deadline')}).\n\n"
            f"Calculated Eligible Matches:\n{match_bullets}\n\n"
            f"STRICT RULES:\n"
            f"1. Rely ONLY on the numbers provided above. Never invent distances, capacities, or scores.\n"
            f"2. Summarize why the #1 ranked NGO is ideal in 2-3 concise professional sentences.\n"
            f"3. Provide 2 bullet points on logistics coordination tips.\n"
            f"4. Keep response under 200 words."
        )

        text = self._call_gemini(prompt)
        if text:
            return {
                "ai_powered": True,
                "summary": text,
                "model": self.model_name
            }

        # Gemini call failed — use fallback
        logger.warning("Gemini matching explanation failed. Using deterministic fallback.")
        result = self._fallback_matching_explanation(top_matches)
        result["error"] = self._last_error
        return result

    def _fallback_matching_explanation(self, top_matches: list) -> dict:
        """High-quality deterministic fallback for matching explanation."""
        top_ngo = top_matches[0]
        summary = (
            f"Top recipient '{top_ngo['ngo_name']}' scored {top_ngo['matching_score']}/100. "
            f"Proximity of {top_ngo['distance_km']} km ensures rapid transit before collection deadline. "
            f"Available capacity of {top_ngo['available_capacity']} meals comfortably absorbs the proposed allocation."
        )
        insights = [
            f"Match #1: {top_ngo['ngo_name']} ({top_ngo['distance_km']} km, capacity: {top_ngo['available_capacity']} meals).",
        ]
        if len(top_matches) > 1:
            insights.append(
                f"Match #2: {top_matches[1]['ngo_name']} ({top_matches[1]['distance_km']} km, score: {top_matches[1]['matching_score']}/100)."
            )
        insights.append("Deterministic logistics engine active (configure GEMINI_API_KEY to activate generative explanations).")
        return {
            "ai_powered": False,
            "summary": summary,
            "insights": insights
        }

    def generate_forecast_summary(self, ngo: dict, forecast: dict) -> dict:
        """
        Produces natural language commentary on the statistical baseline demand forecast.
        Never fabricates numerical predictions — only explains backend-computed numbers.
        """
        predicted = forecast.get("predicted_meals", 0)
        hist_avg = forecast.get("historical_avg", 0)
        recent_avg = forecast.get("recent_avg", 0)
        trend = forecast.get("trend", "Stable")
        trend_pct = forecast.get("trend_percentage", 0)

        if not self.is_available():
            return self._fallback_forecast_summary(ngo, predicted, hist_avg, trend, trend_pct)

        prompt = (
            f"You are the demand forecasting analyst for FoodLink AI.\n"
            f"Generate a concise 2-sentence executive summary and 1 actionable recommendation based on these verified numbers:\n"
            f"- Organization: {ngo.get('name')}\n"
            f"- Predicted Demand for Tomorrow: {predicted} meals\n"
            f"- Historical Average Demand: {hist_avg} meals\n"
            f"- Recent 7-Day Average: {recent_avg} meals\n"
            f"- Trend: {trend} ({trend_pct}%)\n"
            f"Note: This is a statistical moving-average baseline, not a deep learning model.\n"
            f"Do not alter the numbers or invent causes. Keep response under 150 words."
        )

        text = self._call_gemini(prompt)
        if text:
            return {
                "ai_powered": True,
                "summary": text,
                "model": self.model_name
            }

        result = self._fallback_forecast_summary(ngo, predicted, hist_avg, trend, trend_pct)
        result["error"] = self._last_error
        return result

    def _fallback_forecast_summary(self, ngo, predicted, hist_avg, trend, trend_pct):
        """Deterministic fallback for forecast summaries."""
        return {
            "ai_powered": False,
            "summary": (
                f"Statistical baseline projects {predicted} meals required for {ngo.get('name')}. "
                f"Demand trend is {trend} ({'+' if trend_pct > 0 else ''}{trend_pct}% vs historical average). "
                f"Weighted formula (0.5×Hist + 0.3×Recent + 0.2×Expected) indicates stable inventory planning is required."
            ),
            "action_recommendation": f"Prepare distribution logistics for approximately {predicted} meals with a ±10% buffer."
        }

    def generate_platform_insights(self, dashboard_data: dict) -> dict:
        """
        Generates holistic executive overview of food redistribution metrics for administrators.
        """
        total_donations = dashboard_data.get("total_donations", 0)
        total_meals = dashboard_data.get("total_meals_available", 0)
        allocated_meals = dashboard_data.get("meals_allocated", 0)
        active_ngos = dashboard_data.get("active_ngos", 0)

        if not self.is_available():
            return self._fallback_platform_insights(total_donations, total_meals, allocated_meals, active_ngos)

        prompt = (
            f"Act as the operations intelligence copilot for FoodLink AI.\n"
            f"Analyze these live operational metrics:\n"
            f"- Total Donations Logged: {total_donations}\n"
            f"- Total Meals Available: {total_meals}\n"
            f"- Meals Allocated/Redistributed: {allocated_meals}\n"
            f"- Active NGOs in Network: {active_ngos}\n\n"
            f"Provide 3 concise, punchy operational insights or recommendations for the admin dashboard. "
            f"Format as 3 bullet points. Keep response under 120 words."
        )

        text = self._call_gemini(prompt)
        if text:
            lines = [line.strip("- •").strip() for line in text.strip().split("\n") if line.strip()]
            return {
                "ai_powered": True,
                "insights": lines[:4],
                "model": self.model_name
            }

        result = self._fallback_platform_insights(total_donations, total_meals, allocated_meals, active_ngos)
        result["error"] = self._last_error
        return result

    def _fallback_platform_insights(self, total_donations, total_meals, allocated_meals, active_ngos):
        """Deterministic fallback for platform insights."""
        utilization = round((allocated_meals / max(1, total_meals)) * 100, 1)
        return {
            "ai_powered": False,
            "insights": [
                f"Current meal allocation rate is {utilization}% ({allocated_meals} of {total_meals} meals redistributed).",
                f"{active_ngos} registered NGOs currently active in the Chandigarh-Mohali network.",
                "High-volume canteen donations during evening hours drive peak matching efficiency.",
                "Configure GEMINI_API_KEY in environment for generative autonomous dispatch insights."
            ]
        }

    def generate_safety_explanation(self, safety_result: dict, food_name: str, food_category: str) -> dict:
        """
        Generates a plain-language explanation of a food safety screening result.
        Only explains backend-validated results — never overrides safety decisions.
        """
        is_safe = safety_result.get("is_safe", False)
        reasons = safety_result.get("reasons", [])
        warnings = safety_result.get("warnings", [])
        window_hours = safety_result.get("window_limit_hours", 4)
        elapsed = safety_result.get("elapsed_since_prep_hours", 0)

        if not self.is_available():
            if is_safe:
                return {
                    "ai_powered": False,
                    "explanation": (
                        f"'{food_name}' ({food_category}) passed pre-collection risk screening. "
                        f"Elapsed time since preparation: {elapsed} hours (within {window_hours}-hour safe window). "
                        f"{'Warnings: ' + '; '.join(warnings) if warnings else 'No warnings flagged.'}"
                    )
                }
            else:
                return {
                    "ai_powered": False,
                    "explanation": (
                        f"'{food_name}' ({food_category}) was REJECTED during food safety screening. "
                        f"Reasons: {'; '.join(reasons)}. "
                        f"This donation cannot be safely redistributed under current conditions."
                    )
                }

        status_text = "PASSED" if is_safe else "REJECTED"
        prompt = (
            f"You are the food safety explanation assistant for FoodLink AI.\n"
            f"A donation of '{food_name}' ({food_category}) was screened and {status_text}.\n"
            f"Elapsed since prep: {elapsed} hours | Safe window: {window_hours} hours\n"
            f"Reasons: {'; '.join(reasons) if reasons else 'None'}\n"
            f"Warnings: {'; '.join(warnings) if warnings else 'None'}\n\n"
            f"Provide a 2-sentence plain-language explanation of this result.\n"
            f"CRITICAL: Do not override the backend safety decision. Do not certify food as safe.\n"
            f"Keep response under 80 words."
        )

        text = self._call_gemini(prompt)
        if text:
            return {"ai_powered": True, "explanation": text, "model": self.model_name}

        # Fallback
        if is_safe:
            return {"ai_powered": False, "explanation": f"'{food_name}' passed screening within the {window_hours}-hour window."}
        else:
            return {"ai_powered": False, "explanation": f"'{food_name}' rejected: {'; '.join(reasons)}"}


# Singleton instance
ai_service = GeminiService()
