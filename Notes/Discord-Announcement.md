# Heimdallr Discord Announcement

*Created: 2025-12-07 10:18*

---

## Announcement Post

**Introducing Heimdallr - The All-Seeing Guardian for Your Cloud Infrastructure**

Hey everyone! I'm excited to share an open-source project I've been working on.

**Heimdallr** is a Python server that monitors your AWS services (Amplify, EC2, CloudWatch) and uses LLMs to automatically diagnose issues and suggest fixes.

**What it does:**
- Streams CloudWatch logs in real-time looking for errors
- When issues are detected, sends them to an LLM (GPT-4, Claude, or Gemini) for analysis
- Gets intelligent diagnostics explaining *why* something broke, not just *what* broke
- Can automatically execute remediation actions (with approval)

**Why "Heimdallr"?**
Named after the all-seeing Norse god who guards the Bifrost bridge. We use the Old Norse spelling to distinguish from other projects.

**Tech stack:**
- Python 3.11+ with async/await
- LiteLLM for multi-provider LLM support
- boto3/aiobotocore for AWS
- FastAPI for the management API

**Supported LLM providers:**
- OpenAI (GPT-4o, GPT-5, o-series)
- Anthropic (Claude Opus 4.5, Sonnet 4)
- Google (Gemini 2.5 Pro/Flash)

Check it out: https://github.com/ChameleonLabsLLC/heimdallr

Would love feedback, contributions, or just to hear if this solves a problem you've had!

---

## Short Version (for character-limited channels)

**Heimdallr** - Open-source LLM-powered AWS monitoring

Uses GPT-4/Claude/Gemini to diagnose CloudWatch errors and suggest fixes automatically.

- Real-time log streaming
- Intelligent error analysis
- Multi-provider LLM support
- Auto-remediation (optional)

https://github.com/ChameleonLabsLLC/heimdallr
