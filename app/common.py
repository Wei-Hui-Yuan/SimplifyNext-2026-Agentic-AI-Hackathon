"""
Self-contained model factory + .env loader for NUS Compass.

Ported from lab/_common.py rather than imported from it: this package must
not depend on anything outside compass/ (same reason
lab/section_6_agentcore/agent/agent.py repeats its own model factory instead
of importing lab/_common.py — a deployable unit should not reach outside its
own directory).

  PROVIDER = "groq"      <- free tier, no AWS, no cost. Default.
  PROVIDER = "bedrock"   <- needed for the embedding pipeline regardless of
                             which provider the chat model itself uses.

No other file in this package should read LLM_PROVIDER/GROQ_MODEL/BEDROCK_MODEL
directly — go through chat_model()/model_label() so there is exactly one
place that decides.

One deliberate change from lab/_common.py: the require_*() functions here
raise RuntimeError instead of calling sys.exit(). lab/_common.py's sys.exit()
is correct for a one-shot script (print a friendly sentence, exit 1) — but
this module is also imported by app/server.py, a long-running process. A
sys.exit() inside a FastAPI request handler raises SystemExit, a
BaseException that bypasses normal exception handling and would take down
the entire server on the first request made without credentials configured,
not just fail that one request. CLI entrypoints (demo_cli.py, the
data_pipeline scripts) catch RuntimeError at their own top level and exit
the same friendly way; server.py converts it to a clean 503 response instead.
"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Read compass/.env into the environment, if it exists. A real env var
    always wins — this only fills in what is missing."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()

PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
MODEL_ID = os.environ.get(
    "BEDROCK_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
)
EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL", "amazon.titan-embed-text-v2:0")
REGION = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get(
    "AWS_REGION", "ap-southeast-1"
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def model_label() -> str:
    return f"{PROVIDER}:{GROQ_MODEL if PROVIDER == 'groq' else MODEL_ID}"


def require_groq_key() -> None:
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError(
            "No GROQ_API_KEY found.\n\n"
            "  1. Sign in at https://console.groq.com  (free, no card)\n"
            "  2. API Keys -> Create API Key -> copy it NOW (shown once)\n"
            "  3. echo 'GROQ_API_KEY=gsk_...' > compass/.env\n"
        )


def groq_client():
    require_groq_key()
    from groq import Groq

    return Groq()


def require_aws_credentials() -> None:
    import boto3

    try:
        creds = boto3.Session().get_credentials()
        has_creds = creds is not None and bool(creds.access_key)
    except Exception:  # noqa: BLE001 -- e.g. botocore.exceptions.ProfileNotFound if
        # AWS_PROFILE in .env points at a profile that doesn't exist on this
        # machine. boto3.Session() can raise here, not just return None, so
        # this must be a try/except and not a plain None-check -- an AWS
        # config problem should fall back the same way a missing key does,
        # not crash the caller (data_pipeline/build_embeddings.py's Bedrock
        # -> TF-IDF fallback depends on this raising cleanly).
        has_creds = False
    if not has_creds:
        raise RuntimeError(
            "No AWS credentials found.\n\n"
            "  Fix with ONE of:\n"
            "    export AWS_ACCESS_KEY_ID=...  AWS_SECRET_ACCESS_KEY=...\n"
            "    aws sso login --profile <your-profile>\n"
            "    remove/comment out AWS_PROFILE in .env if it points at a profile you don't have\n\n"
            f"  Region currently resolves to: {REGION}\n"
            "  Set it with: export AWS_DEFAULT_REGION=ap-southeast-1\n"
        )


def bedrock_runtime():
    import boto3
    from botocore.config import Config

    require_aws_credentials()
    return boto3.client(
        "bedrock-runtime",
        config=Config(
            region_name=REGION,
            read_timeout=300,
            connect_timeout=120,
            retries={"max_attempts": 1},
        ),
    )


def require_supabase_config() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "No Supabase config found.\n\n"
            "  1. Create a project at https://supabase.com\n"
            "  2. Project Settings -> API -> copy the URL and the service_role key\n"
            "  3. echo 'SUPABASE_URL=...' >> compass/.env\n"
            "     echo 'SUPABASE_KEY=...' >> compass/.env\n\n"
            "  Then run data_pipeline/init_supabase.sql in the Supabase SQL editor.\n"
        )


def chat_model(temperature: float = 0.0, **kwargs):
    """A LangChain chat model for whichever provider PROVIDER names.

    Both objects implement the same BaseChatModel interface: .invoke(),
    .bind_tools(), .with_structured_output() work identically either way.
    """
    if PROVIDER == "groq":
        require_groq_key()
        from langchain_groq import ChatGroq

        return ChatGroq(model=GROQ_MODEL, temperature=temperature, **kwargs)

    if PROVIDER == "bedrock":
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model_id=MODEL_ID,
            client=bedrock_runtime(),
            temperature=temperature,
            **kwargs,
        )

    raise RuntimeError(f"Unknown PROVIDER {PROVIDER!r}. Use 'groq' or 'bedrock'.")


def report_usage(label: str, usage) -> None:
    if usage is None:
        return
    if not isinstance(usage, dict):
        usage = getattr(usage, "model_dump", lambda: vars(usage))()

    def pick(*names):
        for n in names:
            if usage.get(n):
                return usage[n]
        return 0

    inp = pick("input_tokens", "inputTokens", "prompt_tokens")
    out = pick("output_tokens", "outputTokens", "completion_tokens")
    print(f"  [{label}] input={inp} output={out} total={inp + out}")


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")
