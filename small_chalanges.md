ChallengePrizeHow it links**Verda**$10k cloud creditsTheir page literally says *“Run thousands of rollouts in your AfterQuery RL environment and fine-tune a smaller model on the experience.”* That’s the AfterQuery tiebreaker. Requirement: document the process and post a summary in their Discord.**Gemma**€1,000 (top 3, no ranking)**Gemma is the small model you fine-tune** for the tiebreaker. One piece of work counts for AfterQuery, Verda and Gemma.**Gemini API**€4,000 + cloud creditsRun **Gemini as one of the frontier agents** in your environment and analyze where it fails. Being the agent you’re studying is meaningful use, not decoration.**Modal**$2,000 cash + creditsAn alternative or extra compute option: sandboxes for agent runs, batch rollouts, fine-tuning. **Use Verda or Modal as your main compute, not both just to tick boxes.** Verda fits slightly better because it names AfterQuery directly.

### Cheap add-ons (a small effort each)

- **OpenAI Codex** ($10k API credits): use Codex while building and show how. Zero extra product work.
- **Entire** (projector): use it as your Git and agent workflow.
- **CRACI** (LEGO): run your CI on `runs-on: craci`. Bonus: a CI job that runs the evaluation automatically **also proves reproducibility**, which helps AfterQuery’s “Craft” score.
- **Aiven** (€1,000): store rollout logs in **Aiven ClickHouse** to analyze agent mistakes. That feeds your “meaningful difficulty” explanation. Use this *instead of* Tiger Data, since it’s the same idea with a bigger prize.
- **Nemotron** (RTX 5080): test it as a second frontier agent. It’s optional; the free tier is rate-limited, so only add it if your runs are already working.

### Skip these

Solana, Cloudinary, MongoDB, ElevenLabs, Arduino/Atech (hardware), and **Oxylabs and Context.dev**. Live web data would **break reproducibility**, and AfterQuery judges rerun your evaluation themselves.

### The story that ties it together

> “We built environment X. Frontier agents like **Gemini** consistently fail at Y because of Z. We ran thousands of rollouts on **Verda**, fine-tuned **Gemma** on our reference solution’s experience, and Gemma improved by N%. Reproducible in one command, CI on **CRACI**, built with **Codex** + **Entire**.”

**Two warnings:**

1. **The evaluation must run without external services.** The judges rerun it with the standard harness, so Aiven or any cloud logging should be optional, never required for the score.
2. The page shows **“Status: Closed”** at the top. Ask the organizers whether you still need to register for tech challenges, and check each one’s submission requirements (Verda wants a Discord post, Nemotron wants a text explanation, and so on).

Order of work: **make the environment and the gap work first**, then Gemini runs, then Verda + Gemma fine-tuning, then the add-ons.