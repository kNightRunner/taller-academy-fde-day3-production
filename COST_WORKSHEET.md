# Lab 3.4 — Hosted prompt caching: worksheet and experiment plan

**Status:** Mathematical illustration only; **not API-measured data**. Anthropic prompt cache writes and reads are API-specific billing features. Ollama does not provide equivalent `cache_creation_input_tokens` and `cache_read_input_tokens`; reporting either for a local run would be invented.

Run `python cost_lab.py` **with a valid Anthropic API key** to obtain the three actual per-call tables and the required extensions. That script uses the API's `response.usage` fields. The examples below are clearly labeled **hypothetical**.

## Expected table shapes

| Experiment | Call 1: write/read/fresh | Call 2: write/read/fresh | Call 3: write/read/fresh |
|---|---|---|---|
| Stable cached prefix | `measured / measured / measured` | `measured / measured / measured` | `measured / measured / measured` |
| No caching | `0 / 0 / measured` | `0 / 0 / measured` | `0 / 0 / measured` |
| Requested but broken | `measured / measured / measured` | `measured / measured / measured` | `measured / measured / measured` |

These table cells intentionally contain no fabricated values. The script prints actual values whenever the hosted API is available.

## Four observations and calculations

1. **Hypothetical savings.** Suppose a stable cacheable prefix has P = **3,000 tokens**, used in three calls, and ignore short variable inputs and outputs. Without caching: 3P = **9,000 full-price-token equivalents**. With cache: first write 1.25P and two reads at 0.10P each = **4,350**. Savings = (9,000 − 4,350) / 9,000 = **51.7%** on this prefix component alone. This is *not* a result from `response.usage`.
2. **First-call premium/break-even.** A cache write is 1.25× a fresh input, making the first cached call 25% more expensive on this prefix. With two total calls, 1.25P + 0.10P = 1.35P versus 2.00P, so the second call amortizes the first write (assuming same stable cached prefix and no expiry).
3. **Silent cache miss.** A changing timestamp in the cached prefix invalidates an exact prefix match. Monitor `cache_read_input_tokens`, hit rate and `cache_creation_input_tokens` rather than assuming `cache_control` means a hit. The script checks whether read tokens actually increased, not merely whether a flag was passed.
4. **10,000-run projection.** If each run has twelve model calls sharing the same P=3,000-token policy prefix, an uncached run processes 12P = 36,000 full-price equivalents; the cached prefix costs 1.25P + 11×0.10P = 2.35P = 7,050 equivalents. Across 10,000 runs: **360,000,000** vs **70,500,000**, a **289,500,000** equivalent-token difference. At the lab's illustrative $5 per million input tokens, the prefix-only savings would be **$1,447.50**. This excludes variable context, output tokens, TTL and vendor pricing differences. Once Lab 3.2 supplies an observed mean tokens/run, use it as the actual usage baseline instead of assuming all tokens are cacheable.

## Required variants

- **(a) Move timestamp:** Moving a timestamp after an *explicit cache breakpoint* allows the earlier stable prefix to be reused. Moving it merely to the end of the **same single cached system block** may still invalidate that cached block; test the actual API behavior. The general rule is: keep volatile data *outside* the cacheable prefix, not simply further right in a string.
- **(b) Shuffle tools:** Tool definitions can be part of the cached prompt prefix. Shuffling their order may change the prefix and destroy reuse. Serialize a stable ordered list for repeated tasks and compare actual cache-read counts.
- **(c) Two sections:** A short prefix may fall below a model's cacheable-token minimum and result in **zero cache creation/read**, without a protocol error. Do not assume caching succeeded merely because the call returned a normal answer.

**Limits:** This file does not claim the three measured token tables have been completed. To satisfy the measurement requirement, a hosted Anthropic run is necessary; **never publish the API key or raw credentials in GitHub**.