"""Environment defaults are safe and never require an AI account."""
from pathlib import Path
import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, ConfigDict, model_validator
from scripts.provider_common import config, ROOT

class AISettings(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    provider: Literal['off', 'local', 'openai', 'hybrid'] = 'off'
    automated: bool = False
    openai_automated: bool = False
    escalation: bool = False
    local_base_url: str = 'http://localhost:1234/v1'
    local_model: str = ''
    openai_model: str = 'gpt-5.4-nano-2026-03-17'
    escalation_model: str = ''
    daily_budget: float = Field(default=1, ge=0, le=100)
    monthly_budget: float = Field(default=15, ge=0, le=1000)
    calls_per_hour: int = Field(default=10, ge=0, le=1000)
    max_output_tokens: int = Field(default=1200, ge=64, le=8000)
    max_input_chars: int = Field(default=24000, ge=500, le=100000)
    prompt_version: str = 'financial-text-v1'
    escalation_tasks: list[str] = Field(default_factory=lambda: ['contradiction', 'semantic_disagreement'])
    escalation_min_chars: int = Field(default=12000, ge=1000)
    watch_terms: list[str] = Field(default_factory=lambda: ['earnings','guidance','revenue','nuclear','robotics','semiconductor','power','inflation','bitcoin','supply','backlog','margin','regulation'])

    @model_validator(mode='after')
    def local_only(self):
        u = urlsplit(self.local_base_url)
        if u.scheme not in ('http', 'https') or u.hostname not in ('localhost','127.0.0.1','::1','host.docker.internal') or u.username or u.password or u.query or u.fragment:
            raise ValueError('Local AI must use a loopback endpoint or host.docker.internal')
        return self

def environment_ai() -> AISettings:
    c = config()
    def flag(name): return str(c.get(name, 'false')).lower() == 'true'
    return AISettings(provider=c.get('LLM_PROVIDER','off'), automated=flag('LLM_AUTOMATED_ANALYSIS_ENABLED'),
        openai_automated=flag('OPENAI_AUTOMATED_ANALYSIS_ENABLED'),
        escalation=flag('OPENAI_ESCALATION_ENABLED') or flag('OPENAI_ESCALATION_MODEL_ENABLED'),
        local_base_url=c.get('LOCAL_LLM_BASE_URL') or 'http://localhost:1234/v1', local_model=c.get('LOCAL_LLM_MODEL',''),
        openai_model=c.get('OPENAI_MODEL') or 'gpt-5.4-nano-2026-03-17', escalation_model=c.get('OPENAI_ESCALATION_MODEL',''),
        daily_budget=float(c.get('OPENAI_DAILY_BUDGET_USD') or 1), monthly_budget=float(c.get('OPENAI_MONTHLY_BUDGET_USD') or 15),
        calls_per_hour=int(c.get('OPENAI_MAX_CALLS_PER_HOUR') or 10))

def database_url():
    return config().get('DATABASE_URL') or 'sqlite:///' + str(ROOT / 'data/traderx.db')

def ai_environment_fingerprint():
    """Non-secret defaults identify deliberate .env routing changes across restarts."""
    return hashlib.sha256(json.dumps(environment_ai().model_dump(),sort_keys=True).encode()).hexdigest()
