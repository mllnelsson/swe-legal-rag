from agent_kit.config._document import (
    CONFIG_FILENAME,
    CONFIG_PATH_ENV,
    SUPPORTED_VERSION,
    LLMConfigDocument,
    ProviderSpec,
    RoleDefaults,
    RoleSpec,
)
from agent_kit.config._loader import (
    api_key_for,
    env_alias,
    find_config_path,
    get_llm_config,
    load_config_document,
    resolve_role_config,
    role_model_env_var,
    without_env_overrides,
)
from agent_kit.config._roles import create_llm_provider, llm_role_is_disabled

__all__ = [
    "CONFIG_FILENAME",
    "CONFIG_PATH_ENV",
    "SUPPORTED_VERSION",
    "LLMConfigDocument",
    "ProviderSpec",
    "RoleDefaults",
    "RoleSpec",
    "find_config_path",
    "get_llm_config",
    "load_config_document",
    "resolve_role_config",
    "role_model_env_var",
    "create_llm_provider",
    "llm_role_is_disabled",
    # Precedence helpers a host reuses when it resolves its own settings (e.g.
    # embedding config) with the same "environment wins" rule.
    "api_key_for",
    "env_alias",
    "without_env_overrides",
]
